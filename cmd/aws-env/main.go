package main

import (
	"flag"
	"fmt"
	"os"
	"strings"
	"time"

	tea "charm.land/bubbletea/v2"
)

func main() {
	if len(os.Args) < 2 {
		printUsage()
		os.Exit(1)
	}

	switch os.Args[1] {
	case "set":
		runSet(os.Args[2:])
	case "profile":
		runProfile(os.Args[2:])
	case "region":
		runRegion(os.Args[2:])
	case "show":
		runShow()
	case "token-status":
		runTokenStatus(os.Args[2:])
	case "--help", "-h", "help":
		printUsage()
	default:
		fmt.Fprintf(os.Stderr, "aws-env: unknown command %q\n\n", os.Args[1])
		printUsage()
		os.Exit(1)
	}
}

func printUsage() {
	fmt.Fprint(os.Stderr, `Usage: aws-env <command> [flags]

Commands:
  set           Select profile then region (prints export lines to stdout)
  profile       Select profile only
  region        Select region only
  show          Display current AWS environment variables
  token-status  Check AWS token expiration

Flags for set/profile:
  --profile-query, --query  Initial filter text

Flags for set/region:
  --region-query            Initial region filter (default: "us-")

Flags for token-status:
  --profile                 Profile to check (default: SAML2AWS_PROFILE > AWS_SSO_PROFILE > AWS_PROFILE > default)

Use with eval in your shell wrapper:
  eval "$(aws-env set)"
  eval "$(aws-env profile)"
  eval "$(aws-env region)"
`)
}

var profileEnvPriority = []string{"SAML2AWS_PROFILE", "AWS_SSO_PROFILE", "AWS_PROFILE"}

func activeProfile() string {
	if p := firstEnv(profileEnvPriority...); p != "" {
		return p
	}
	return "default"
}

func runPicker(title string, loader func() ([]string, error), initialQuery string) (selected string, aborted bool) {
	m := newPickerModel(title, loader, initialQuery)
	p := tea.NewProgram(m, tea.WithOutput(os.Stderr))
	final, err := p.Run()
	if err != nil {
		fmt.Fprintf(os.Stderr, "aws-env: %v\n", err)
		os.Exit(1)
	}
	fm := final.(pickerModel)
	if fm.err != nil {
		fmt.Fprintf(os.Stderr, "aws-env: %v\n", fm.err)
		os.Exit(1)
	}
	return fm.Selected, fm.Aborted
}

func mustSelect(title string, loader func() ([]string, error), query, noun string) string {
	selected, aborted := runPicker(title, loader, query)
	if aborted || selected == "" {
		fmt.Fprintf(os.Stderr, "AWS %s not updated.\n", noun)
		os.Exit(1)
	}
	return selected
}

func runSet(args []string) {
	fs := flag.NewFlagSet("set", flag.ExitOnError)
	pq := fs.String("profile-query", "", "Initial profile filter")
	rq := fs.String("region-query", "us-", "Initial region filter")
	_ = fs.Parse(args)

	profile := mustSelect("aws-env — select profile", listProfiles, *pq, "profile")
	region := mustSelect("aws-env — select region", func() ([]string, error) {
		return regionDisplayItems(), nil
	}, *rq, "region")

	code := regionCode(region)
	fmt.Printf("export AWS_PROFILE=%s\n", shellQuote(profile))
	fmt.Printf("export AWS_DEFAULT_REGION=%s\n", shellQuote(code))
	fmt.Printf("export AWS_REGION=%s\n", shellQuote(code))
}

func runProfile(args []string) {
	fs := flag.NewFlagSet("profile", flag.ExitOnError)
	q := fs.String("query", "", "Initial filter")
	_ = fs.Parse(args)
	profile := mustSelect("aws-env — select profile", listProfiles, *q, "profile")
	fmt.Printf("export AWS_PROFILE=%s\n", shellQuote(profile))
}

func runRegion(args []string) {
	fs := flag.NewFlagSet("region", flag.ExitOnError)
	q := fs.String("query", "us-", "Initial filter")
	_ = fs.Parse(args)
	region := mustSelect("aws-env — select region", func() ([]string, error) {
		return regionDisplayItems(), nil
	}, *q, "region")
	code := regionCode(region)
	fmt.Printf("export AWS_DEFAULT_REGION=%s\n", shellQuote(code))
	fmt.Printf("export AWS_REGION=%s\n", shellQuote(code))
}

func runShow() {
	type envVar struct{ k, v string }
	vars := []envVar{
		{"AWS_PROFILE", os.Getenv("AWS_PROFILE")},
		{"AWS_DEFAULT_PROFILE", os.Getenv("AWS_DEFAULT_PROFILE")},
		{"AWS_REGION", os.Getenv("AWS_REGION")},
		{"AWS_DEFAULT_REGION", os.Getenv("AWS_DEFAULT_REGION")},
		{"AWS_ACCESS_KEY_ID", os.Getenv("AWS_ACCESS_KEY_ID")},
		{"AWS_SECRET_ACCESS_KEY", maskSecret(os.Getenv("AWS_SECRET_ACCESS_KEY"))},
		{"AWS_SESSION_TOKEN", maskSecret(os.Getenv("AWS_SESSION_TOKEN"))},
		{"AWS_SECURITY_TOKEN", maskSecret(os.Getenv("AWS_SECURITY_TOKEN"))},
	}
	any := false
	for _, v := range vars {
		if v.v != "" {
			fmt.Printf("%-25s %s\n", v.k, v.v)
			any = true
		}
	}
	if !any {
		fmt.Println("No AWS environment variables set.")
	}

	// Append token status if available for the active profile.
	p := activeProfile()
	if expiry, err := readTokenExpiry(p); err == nil {
		diff := time.Until(expiry)
		local := expiry.Local().Format("15:04")
		var status string
		switch {
		case diff < 0:
			status = fmt.Sprintf("EXPIRED %dm ago", int(-diff.Minutes()))
		case diff < 5*time.Minute:
			status = fmt.Sprintf("expires in %dm (%s) — renew soon", int(diff.Minutes()), local)
		case diff < time.Hour:
			status = fmt.Sprintf("expires in %dm (%s)", int(diff.Minutes()), local)
		default:
			status = fmt.Sprintf("valid %dh %dm (expires %s)", int(diff.Hours()), int(diff.Minutes())%60, local)
		}
		fmt.Printf("%-25s %s\n", "AWS_TOKEN_TTL", status)
	}
}

func runTokenStatus(args []string) {
	fs := flag.NewFlagSet("token-status", flag.ExitOnError)
	profile := fs.String("profile", "", "AWS profile to check")
	_ = fs.Parse(args)

	p := *profile
	if p == "" {
		p = activeProfile()
	}

	expiry, err := readTokenExpiry(p)
	if err != nil {
		fmt.Fprintf(os.Stderr, "aws-env: %v\n", err)
		os.Exit(1)
	}

	now := time.Now()
	diff := expiry.Sub(now)
	local := expiry.Local().Format("15:04")

	if diff < 0 {
		fmt.Printf("Token EXPIRED %d minutes ago\n", int(-diff.Minutes()))
		fmt.Println("Run 'saml2aws login' to refresh")
		os.Exit(1)
	}

	h := int(diff.Hours())
	m := int(diff.Minutes()) % 60

	switch {
	case diff < 5*time.Minute:
		fmt.Printf("Token expires in %dm (%s) — run 'saml2aws login' soon\n", int(diff.Minutes()), local)
	case diff < time.Hour:
		fmt.Printf("Token expires in %dm (%s)\n", int(diff.Minutes()), local)
	default:
		fmt.Printf("Token valid for %dh %dm (expires %s)\n", h, m, local)
	}
}

func maskSecret(s string) string {
	if len(s) == 0 {
		return ""
	}
	if len(s) <= 5 {
		return "*****"
	}
	return s[:5] + "*****"
}

func firstEnv(keys ...string) string {
	for _, k := range keys {
		if v := strings.TrimSpace(os.Getenv(k)); v != "" {
			return v
		}
	}
	return ""
}

func shellQuote(s string) string {
	if !strings.ContainsAny(s, " \t\n\"'\\$`!") {
		return s
	}
	return "'" + strings.ReplaceAll(s, "'", "'\\''") + "'"
}
