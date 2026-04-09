package main

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"gopkg.in/yaml.v3"
)

const envDisabled = "TOOLBOX_SHELL_DISABLED"
const envEnabled = "TOOLBOX_SHELL_ENABLED"

// shellFile is the filename under the toolbox config directory.
const shellFile = "shell.yaml"

// shellConfig is the on-disk shell.yaml shape.
type shellConfig struct {
	DisabledModules []string `yaml:"disabled_modules"`
}

func shellConfigDir() (string, error) {
	base := os.Getenv("XDG_CONFIG_HOME")
	if base == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			return "", err
		}
		base = filepath.Join(home, ".config")
	}
	return filepath.Join(base, "silentcastle", "toolbox"), nil
}

// shellConfigPath returns the absolute path to shell.yaml.
func shellConfigPath() (string, error) {
	dir, err := shellConfigDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(dir, shellFile), nil
}

// loadShellConfig reads shell.yaml, creating an empty config if the file is missing.
func loadShellConfig() (*shellConfig, string, error) {
	p, err := shellConfigPath()
	if err != nil {
		return nil, "", err
	}
	data, err := os.ReadFile(p)
	if err != nil {
		if os.IsNotExist(err) {
			return &shellConfig{}, p, nil
		}
		return nil, p, err
	}
	var c shellConfig
	if err := yaml.Unmarshal(data, &c); err != nil {
		return nil, p, err
	}
	return &c, p, nil
}

// saveShellConfig writes shell.yaml (creates directory if needed).
func saveShellConfig(c *shellConfig) error {
	p, err := shellConfigPath()
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
		return err
	}
	data, err := yaml.Marshal(c)
	if err != nil {
		return err
	}
	return os.WriteFile(p, data, 0o644)
}

func parseCommaSet(s string) map[string]struct{} {
	out := make(map[string]struct{})
	for _, part := range strings.Split(s, ",") {
		part = strings.TrimSpace(part)
		if part != "" {
			out[part] = struct{}{}
		}
	}
	return out
}

// effectiveDisabled returns stems that should not be sourced (file ∪ env_disabled \ env_enabled).
func effectiveDisabled(file *shellConfig) map[string]struct{} {
	disabled := make(map[string]struct{})
	for _, s := range file.DisabledModules {
		s = strings.TrimSpace(s)
		if s != "" {
			disabled[s] = struct{}{}
		}
	}
	for s := range parseCommaSet(os.Getenv(envDisabled)) {
		disabled[s] = struct{}{}
	}
	for s := range parseCommaSet(os.Getenv(envEnabled)) {
		delete(disabled, s)
	}
	return disabled
}

// effectiveDisabledList returns sorted disabled stems (for stable output).
func effectiveDisabledList(file *shellConfig) []string {
	set := effectiveDisabled(file)
	list := make([]string, 0, len(set))
	for s := range set {
		list = append(list, s)
	}
	sort.Strings(list)
	return list
}

// addDisabledModules adds stems to the file config (idempotent).
func addDisabledModules(file *shellConfig, stems ...string) error {
	have := make(map[string]struct{})
	for _, s := range file.DisabledModules {
		have[strings.TrimSpace(s)] = struct{}{}
	}
	for _, s := range stems {
		s = strings.TrimSpace(s)
		if s == "" {
			continue
		}
		if _, ok := have[s]; !ok {
			file.DisabledModules = append(file.DisabledModules, s)
			have[s] = struct{}{}
		}
	}
	sort.Strings(file.DisabledModules)
	return saveShellConfig(file)
}

// removeDisabledModules removes stems from the file config.
func removeDisabledModules(file *shellConfig, stems ...string) error {
	rm := make(map[string]struct{})
	for _, s := range stems {
		rm[strings.TrimSpace(s)] = struct{}{}
	}
	keep := file.DisabledModules[:0]
	for _, s := range file.DisabledModules {
		if _, drop := rm[s]; drop {
			continue
		}
		keep = append(keep, s)
	}
	file.DisabledModules = keep
	return saveShellConfig(file)
}

// moduleStems returns unique stems from shell/modules (*.sh and *.zsh).
func moduleStems(toolboxRoot string) ([]string, error) {
	modDir := filepath.Join(toolboxRoot, "shell", "modules")
	ents, err := os.ReadDir(modDir)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}
	set := make(map[string]struct{})
	for _, e := range ents {
		if e.IsDir() {
			continue
		}
		name := e.Name()
		var stem string
		switch {
		case strings.HasSuffix(name, ".sh"):
			stem = strings.TrimSuffix(name, ".sh")
		case strings.HasSuffix(name, ".zsh"):
			stem = strings.TrimSuffix(name, ".zsh")
		default:
			continue
		}
		if stem != "" {
			set[stem] = struct{}{}
		}
	}
	out := make([]string, 0, len(set))
	for s := range set {
		out = append(out, s)
	}
	sort.Strings(out)
	return out, nil
}

// validateModuleStems returns an error if any stem is not a known module.
func validateModuleStems(toolboxRoot string, stems []string) error {
	valid, err := moduleStems(toolboxRoot)
	if err != nil {
		return err
	}
	ok := make(map[string]struct{}, len(valid))
	for _, s := range valid {
		ok[s] = struct{}{}
	}
	var bad []string
	for _, s := range stems {
		s = strings.TrimSpace(s)
		if s == "" {
			continue
		}
		if _, exists := ok[s]; !exists {
			bad = append(bad, s)
		}
	}
	if len(bad) > 0 {
		return fmt.Errorf("unknown module stem(s): %s (see shell/modules/)", strings.Join(bad, ", "))
	}
	return nil
}
