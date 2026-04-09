package main

import (
	"fmt"
	"strings"
	"time"

	"charm.land/bubbles/v2/spinner"
	"charm.land/bubbles/v2/textinput"
	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
)

var (
	ssmTitleStyle = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("99"))
	ssmHelpStyle  = lipgloss.NewStyle().Foreground(lipgloss.Color("240"))
	ssmErrorStyle = lipgloss.NewStyle().Foreground(lipgloss.Color("196"))
	ssmDimStyle   = lipgloss.NewStyle().Foreground(lipgloss.Color("244"))
	ssmSelStyle   = lipgloss.NewStyle().Foreground(lipgloss.Color("212")).Bold(true)
	ssmPanelStyle = lipgloss.NewStyle().
			BorderStyle(lipgloss.NormalBorder()).
			BorderForeground(lipgloss.Color("236")).
			Padding(0, 1)
)

type appState int

const (
	stateLoading appState = iota
	stateReady
	stateError
)

type errMsg struct {
	err error
}

type instancesLoadedMsg struct {
	instances []Instance
	source    string
	cachedAt  time.Time
	err       error
}

type ssmInfoLoadedMsg struct {
	gen  int
	info map[string]SSMInstanceInfo
	err  error
}

type sessionEndedMsg struct {
	instanceID string
	err        error
}

type model struct {
	opts options

	state appState

	width  int
	height int

	filter      textinput.Model
	filterFocus bool
	spinner     spinner.Model

	instances []Instance
	filtered  []Instance
	cursor    int

	// EC2 state filter: when true, only running instances (default, matches Python).
	filterRunningOnly bool
	// When true, only instances returned by SSM describe-instance-information.
	filterSSMOnly bool

	ssmGen     int
	ssmLoading bool
	ssmLoaded  bool
	ssmInfo    map[string]SSMInstanceInfo

	status   string
	cacheSrc string
	cachedAt time.Time
	err      error
}

func newModel(opts options) (model, error) {
	cache, err := cachePath(opts.profile, opts.region)
	if err != nil {
		return model{}, err
	}

	ti := textinput.New()
	ti.Placeholder = "Search: name, id, IP, state, type, key, SSM ping / platform…"
	ti.SetValue(opts.query)
	ti.Blur()

	sp := spinner.New()
	sp.Spinner = spinner.Dot

	return model{
		opts:              opts,
		state:             stateLoading,
		filter:            ti,
		spinner:           sp,
		filterRunningOnly: true,
		ssmInfo:           make(map[string]SSMInstanceInfo),
		status:            fmt.Sprintf("Loading instances for %s / %s", opts.profile, opts.region),
		cacheSrc:          cache,
	}, nil
}

func (m model) Init() tea.Cmd {
	return tea.Batch(m.spinner.Tick, loadInstancesCmd(m.opts))
}

func loadInstancesCmd(opts options) tea.Cmd {
	return func() tea.Msg {
		cacheFile, err := cachePath(opts.profile, opts.region)
		if err != nil {
			return errMsg{err: err}
		}

		if !opts.forceRefresh && !cacheExpired(cacheFile, opts.ttl) {
			instances, cachedAt, err := loadCachedInstances(cacheFile)
			if err == nil {
				return instancesLoadedMsg{
					instances: instances,
					source:    "cache",
					cachedAt:  cachedAt,
				}
			}
		}

		instances, err := fetchInstances(opts.profile, opts.region)
		if err != nil {
			if cached, cachedAt, loadErr := loadCachedInstances(cacheFile); loadErr == nil {
				return instancesLoadedMsg{
					instances: cached,
					source:    "stale-cache",
					cachedAt:  cachedAt,
					err:       err,
				}
			}
			return errMsg{err: err}
		}

		if err := writeCachedInstances(cacheFile, instances); err != nil && opts.debug {
			return errMsg{err: err}
		}

		return instancesLoadedMsg{
			instances: instances,
			source:    "aws",
			cachedAt:  time.Now(),
		}
	}
}

func instanceIDs(insts []Instance) []string {
	out := make([]string, 0, len(insts))
	for _, i := range insts {
		if i.InstanceID != "" {
			out = append(out, i.InstanceID)
		}
	}
	return out
}

func loadSSMInfoCmd(opts options, ids []string, gen int) tea.Cmd {
	return func() tea.Msg {
		info, err := fetchSSMInstanceInformation(opts.profile, opts.region, ids)
		if info == nil {
			info = map[string]SSMInstanceInfo{}
		}
		return ssmInfoLoadedMsg{gen: gen, info: info, err: err}
	}
}

func startSessionCmd(profile, region string, inst Instance) tea.Cmd {
	return tea.ExecProcess(runSession(profile, region, inst.InstanceID), func(err error) tea.Msg {
		return sessionEndedMsg{
			instanceID: inst.InstanceID,
			err:        err,
		}
	})
}

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
		m.filter.SetWidth(max(20, msg.Width-4))
		return m, nil

	case errMsg:
		m.state = stateError
		m.err = msg.err
		m.status = msg.err.Error()
		return m, nil

	case instancesLoadedMsg:
		if msg.err != nil {
			m.status = fmt.Sprintf("Loaded %d instances from %s after refresh failed", len(msg.instances), msg.source)
		} else {
			switch msg.source {
			case "cache":
				m.status = fmt.Sprintf("Loaded %d instances from cache", len(msg.instances))
			case "aws":
				m.status = fmt.Sprintf("Loaded %d instances from AWS", len(msg.instances))
			default:
				m.status = fmt.Sprintf("Loaded %d instances", len(msg.instances))
			}
		}
		m.instances = msg.instances
		m.cachedAt = msg.cachedAt
		m.cacheSrc = msg.source
		m.state = stateReady
		m.err = nil
		m.ssmGen++
		gen := m.ssmGen
		m.ssmLoaded = false
		m.ssmLoading = true
		m.ssmInfo = make(map[string]SSMInstanceInfo)
		m.applyFilter()
		return m, loadSSMInfoCmd(m.opts, instanceIDs(m.instances), gen)

	case ssmInfoLoadedMsg:
		m.ssmLoading = false
		if msg.gen != m.ssmGen {
			return m, nil
		}
		m.ssmInfo = msg.info
		m.ssmLoaded = true
		if msg.err != nil {
			m.status = fmt.Sprintf("%s — SSM: %v", m.status, msg.err)
		}
		m.applyFilter()
		return m, nil

	case sessionEndedMsg:
		if msg.err != nil {
			m.status = fmt.Sprintf("SSM session for %s ended with error: %v", msg.instanceID, msg.err)
		} else {
			m.status = fmt.Sprintf("SSM session for %s ended", msg.instanceID)
		}
		return m, nil

	case tea.KeyPressMsg:
		if msg.String() == "ctrl+c" {
			return m, tea.Quit
		}
	}

	if m.state == stateLoading {
		var cmd tea.Cmd
		m.spinner, cmd = m.spinner.Update(msg)
		return m, cmd
	}

	if m.filterFocus {
		switch msg := msg.(type) {
		case tea.KeyPressMsg:
			switch msg.String() {
			case "esc":
				m.filter.Blur()
				m.filterFocus = false
				return m, nil
			case "enter":
				m.filter.Blur()
				m.filterFocus = false
				return m, nil
			}
		}

		var cmd tea.Cmd
		m.filter, cmd = m.filter.Update(msg)
		m.applyFilter()
		return m, cmd
	}

	switch msg := msg.(type) {
	case tea.KeyPressMsg:
		switch msg.String() {
		case "q":
			return m, tea.Quit
		case "/":
			m.filterFocus = true
			m.filter.Focus()
			return m, textinput.Blink
		case "r":
			m.ssmGen++
			m.state = stateLoading
			m.status = "Refreshing instances from AWS"
			m.opts.forceRefresh = true
			m.ssmLoaded = false
			m.ssmLoading = true
			m.ssmInfo = make(map[string]SSMInstanceInfo)
			m.applyFilter()
			return m, tea.Batch(m.spinner.Tick, loadInstancesCmd(m.opts))
		case "a":
			m.filterRunningOnly = !m.filterRunningOnly
			m.applyFilter()
			return m, nil
		case "f":
			m.filterSSMOnly = !m.filterSSMOnly
			if m.filterSSMOnly && !m.ssmLoaded && !m.ssmLoading && len(m.instances) > 0 {
				m.ssmGen++
				gen := m.ssmGen
				m.ssmLoading = true
				m.applyFilter()
				return m, loadSSMInfoCmd(m.opts, instanceIDs(m.instances), gen)
			}
			m.applyFilter()
			return m, nil
		case "up", "k":
			if m.cursor > 0 {
				m.cursor--
			}
			return m, nil
		case "down", "j":
			if m.cursor < len(m.filtered)-1 {
				m.cursor++
			}
			return m, nil
		case "enter":
			if len(m.filtered) == 0 {
				return m, nil
			}
			inst := m.filtered[m.cursor]
			if inst.State != "" && inst.State != "running" {
				m.status = fmt.Sprintf("Instance %s is %s; only running instances can start a session", inst.InstanceID, inst.State)
				return m, nil
			}
			m.status = fmt.Sprintf("Starting SSM session for %s", inst.InstanceID)
			return m, startSessionCmd(m.opts.profile, m.opts.region, inst)
		}
	}

	return m, nil
}

func (m *model) instanceTextMatches(inst Instance) bool {
	q := strings.ToLower(strings.TrimSpace(m.filter.Value()))
	if q == "" {
		return true
	}
	var ssm *SSMInstanceInfo
	if info, ok := m.ssmInfo[inst.InstanceID]; ok {
		ssm = &info
	}
	parts := []string{
		inst.Name,
		inst.InstanceID,
		inst.PrivateIP,
		inst.PublicIP,
		inst.State,
		inst.ImageID,
		inst.InstanceType,
		inst.Platform,
		inst.KeyName,
		inst.PublicDNSName,
	}
	if ssm != nil {
		parts = append(parts,
			ssm.PingStatus,
			ssm.PlatformType,
			ssm.PlatformName,
			ssm.AgentVersion,
		)
	} else if m.ssmLoaded {
		parts = append(parts, "ssm n/a")
	}
	haystack := strings.ToLower(strings.Join(parts, "\t"))
	return strings.Contains(haystack, q)
}

func (m *model) applyFilter() {
	prevID := ""
	if m.cursor >= 0 && m.cursor < len(m.filtered) {
		prevID = m.filtered[m.cursor].InstanceID
	}

	filtered := make([]Instance, 0, len(m.instances))
	for _, inst := range m.instances {
		if !m.instanceTextMatches(inst) {
			continue
		}
		if m.filterRunningOnly && !strings.EqualFold(strings.TrimSpace(inst.State), "running") {
			continue
		}
		if m.filterSSMOnly {
			if !m.ssmLoaded {
				continue
			}
			if _, ok := m.ssmInfo[inst.InstanceID]; !ok {
				continue
			}
		}
		filtered = append(filtered, inst)
	}
	m.filtered = filtered
	m.cursor = 0
	if prevID != "" {
		for i, inst := range m.filtered {
			if inst.InstanceID == prevID {
				m.cursor = i
				break
			}
		}
	}
	if len(m.filtered) == 0 {
		m.cursor = 0
		return
	}
	if m.cursor >= len(m.filtered) {
		m.cursor = len(m.filtered) - 1
	}
}

func (m *model) ssmIndicator(id string) string {
	if !m.ssmLoaded {
		return "…"
	}
	info, ok := m.ssmInfo[id]
	if !ok {
		return "×"
	}
	if strings.EqualFold(strings.TrimSpace(info.PingStatus), "online") {
		return "✓"
	}
	return "×"
}

func (m model) View() tea.View {
	if m.width == 0 {
		view := tea.NewView("Loading...")
		view.AltScreen = !m.opts.noAlt
		return view
	}

	var content string
	if m.state == stateLoading {
		content = m.renderLoading()
	} else if m.state == stateError {
		content = m.renderError()
	} else {
		content = m.renderReady()
	}

	view := tea.NewView(content)
	view.AltScreen = !m.opts.noAlt
	return view
}

func (m model) renderLoading() string {
	lines := []string{
		ssmTitleStyle.Render("  ssm-connect"),
		"",
		fmt.Sprintf("  %s %s", m.spinner.View(), m.status),
		"",
		ssmHelpStyle.Render("  Waiting for EC2 instance data..."),
	}
	return strings.Join(lines, "\n")
}

func (m model) renderError() string {
	lines := []string{
		ssmTitleStyle.Render("  ssm-connect"),
		"",
		ssmErrorStyle.Render("  " + m.status),
		"",
		ssmHelpStyle.Render("  Press ctrl+c to exit."),
	}
	return strings.Join(lines, "\n")
}

func (m model) renderReady() string {
	bodyHeight := max(8, m.height-8)
	listWidth := max(32, m.width/2)
	detailWidth := max(32, m.width-listWidth-3)

	left := ssmPanelStyle.Width(listWidth - 2).Height(bodyHeight).Render(m.renderList(listWidth-4, bodyHeight-2))
	right := ssmPanelStyle.Width(detailWidth - 2).Height(bodyHeight).Render(m.renderDetails(detailWidth-4, bodyHeight-2))

	help := "q quit • / search • a running vs all states • f SSM-managed only • j/k move • enter connect • r refresh"
	if m.filterFocus {
		help = "search mode • enter/esc return to list"
	}

	header := []string{
		ssmTitleStyle.Render("  ssm-connect"),
		ssmDimStyle.Render(fmt.Sprintf("  profile=%s  region=%s  source=%s", m.opts.profile, m.opts.region, m.cacheSrc)),
		fmt.Sprintf("  filter: %s", m.filter.View()),
		"",
		lipgloss.JoinHorizontal(lipgloss.Top, left, " ", right),
		"",
		"  " + m.statusLine(),
		"  " + ssmHelpStyle.Render(help),
	}

	return strings.Join(header, "\n")
}

func (m model) renderList(width, height int) string {
	if len(m.filtered) == 0 {
		return ssmDimStyle.Render("No instances match the current filter.")
	}

	start := 0
	if m.cursor >= height {
		start = m.cursor - height + 1
	}
	end := min(len(m.filtered), start+height)

	lines := make([]string, 0, end-start+1)
	for i := start; i < end; i++ {
		inst := m.filtered[i]
		line := fmt.Sprintf("%-3s %-19s %-10s %s",
			m.ssmIndicator(inst.InstanceID),
			inst.InstanceID,
			stateLabel(inst.State),
			instanceName(inst.Name))
		if i == m.cursor {
			lines = append(lines, ssmSelStyle.Render("> "+truncate(line, width-2)))
			continue
		}
		lines = append(lines, "  "+truncate(line, width-2))
	}
	return strings.Join(lines, "\n")
}

func (m model) renderDetails(width, _ int) string {
	if len(m.filtered) == 0 {
		return ssmDimStyle.Render("Select an instance to view details.")
	}

	inst := m.filtered[m.cursor]
	ssmLines := m.renderSSMDetailLines(inst)
	lines := []string{
		ssmTitleStyle.Render(truncate(instanceName(inst.Name), width)),
		"",
		fmt.Sprintf("Instance ID : %s", inst.InstanceID),
		fmt.Sprintf("State       : %s", valueOr(inst.State, "-")),
	}
	lines = append(lines, ssmLines...)
	lines = append(lines,
		fmt.Sprintf("Private IP  : %s", valueOr(inst.PrivateIP, "-")),
		fmt.Sprintf("Public IP   : %s", valueOr(inst.PublicIP, "-")),
		fmt.Sprintf("Public DNS  : %s", valueOr(inst.PublicDNSName, "-")),
		fmt.Sprintf("AMI         : %s", valueOr(inst.ImageID, "-")),
		fmt.Sprintf("Type        : %s", valueOr(inst.InstanceType, "-")),
		fmt.Sprintf("Platform    : %s", valueOr(inst.Platform, "-")),
		fmt.Sprintf("Key Name    : %s", valueOr(inst.KeyName, "-")),
	)

	return strings.Join(lines, "\n")
}

func (m model) renderSSMDetailLines(inst Instance) []string {
	if !m.ssmLoaded {
		return []string{fmt.Sprintf("SSM         : %s", ssmDimStyle.Render("loading…"))}
	}
	info, ok := m.ssmInfo[inst.InstanceID]
	if !ok {
		return []string{fmt.Sprintf("SSM         : %s", ssmDimStyle.Render("not in SSM (no instance information)"))}
	}
	return []string{
		fmt.Sprintf("SSM ping    : %s", valueOr(info.PingStatus, "-")),
		fmt.Sprintf("SSM type    : %s", valueOr(info.PlatformType, "-")),
		fmt.Sprintf("SSM OS      : %s", valueOr(info.PlatformName, "-")),
		fmt.Sprintf("SSM agent   : %s", valueOr(info.AgentVersion, "-")),
	}
}

func (m model) statusLine() string {
	parts := []string{m.status}
	if !m.cachedAt.IsZero() {
		parts = append(parts, "cache "+m.cachedAt.Format("2006-01-02 15:04:05"))
	}
	if len(m.filtered) > 0 {
		parts = append(parts, fmt.Sprintf("%d/%d shown", len(m.filtered), len(m.instances)))
	} else {
		parts = append(parts, fmt.Sprintf("%d instances", len(m.instances)))
	}
	if m.filterRunningOnly {
		parts = append(parts, "running only")
	} else {
		parts = append(parts, "all states")
	}
	if m.filterSSMOnly {
		parts = append(parts, "SSM only")
	}
	return strings.Join(parts, " • ")
}

func instanceName(name string) string {
	if name == "" {
		return "<unnamed>"
	}
	return name
}

func stateLabel(state string) string {
	if state == "" {
		return "-"
	}
	return state
}

func valueOr(value, fallback string) string {
	if strings.TrimSpace(value) == "" {
		return fallback
	}
	return value
}

func truncate(value string, width int) string {
	if width <= 0 {
		return ""
	}
	if lipgloss.Width(value) <= width {
		return value
	}
	if width <= 1 {
		return "…"
	}
	return lipgloss.NewStyle().MaxWidth(width).Render(value)
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}
