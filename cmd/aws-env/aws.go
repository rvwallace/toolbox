package main

import (
	"bufio"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

func listProfiles() ([]string, error) {
	out, err := exec.Command("aws", "configure", "list-profiles").Output()
	if err != nil {
		return nil, fmt.Errorf("aws configure list-profiles: %w", err)
	}
	var profiles []string
	for line := range strings.SplitSeq(strings.TrimSpace(string(out)), "\n") {
		if p := strings.TrimSpace(line); p != "" {
			profiles = append(profiles, p)
		}
	}
	if len(profiles) == 0 {
		return nil, fmt.Errorf("no AWS profiles found — run 'aws configure' to set one up")
	}
	return profiles, nil
}

// readTokenExpiry reads x_security_token_expires from ~/.aws/credentials for the given profile.
func readTokenExpiry(profile string) (time.Time, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return time.Time{}, fmt.Errorf("find home dir: %w", err)
	}
	credsFile := filepath.Join(home, ".aws", "credentials")

	f, err := os.Open(credsFile)
	if os.IsNotExist(err) {
		return time.Time{}, fmt.Errorf("credentials file not found: %s", credsFile)
	}
	if err != nil {
		return time.Time{}, fmt.Errorf("open credentials: %w", err)
	}
	defer f.Close()

	target := "[" + profile + "]"
	inProfile := false
	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if strings.HasPrefix(line, "[") {
			inProfile = line == target
			continue
		}
		if !inProfile {
			continue
		}
		if strings.HasPrefix(line, "x_security_token_expires") {
			parts := strings.SplitN(line, "=", 2)
			if len(parts) != 2 {
				continue
			}
			return parseExpiry(strings.TrimSpace(parts[1]))
		}
	}
	if err := scanner.Err(); err != nil {
		return time.Time{}, fmt.Errorf("read credentials: %w", err)
	}
	return time.Time{}, fmt.Errorf("no token expiration found for [%s] — run 'saml2aws login' to authenticate", profile)
}

var expiryFormats = []string{
	time.RFC3339,
	"2006-01-02T15:04:05Z07:00",
	"2006-01-02 15:04:05+00:00",
	"2006-01-02 15:04:05 +00:00",
	"2006-01-02 15:04:05",
	"2006-01-02T15:04:05",
}

func parseExpiry(s string) (time.Time, error) {
	s = strings.TrimSpace(s)
	// Normalize "2024-01-15 18:30:00 UTC" → "2024-01-15 18:30:00+00:00"
	if strings.HasSuffix(s, " UTC") {
		s = s[:len(s)-4] + "+00:00"
	}
	for _, format := range expiryFormats {
		if t, err := time.Parse(format, s); err == nil {
			return t, nil
		}
	}
	return time.Time{}, fmt.Errorf("cannot parse token expiry time: %q", s)
}
