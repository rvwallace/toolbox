package main

import (
	"flag"
	"fmt"
	"os"
	"os/exec"
	"strings"

	tea "charm.land/bubbletea/v2"
)

type options struct {
	profile      string
	region       string
	query        string
	forceRefresh bool
	ttl          int
	debug        bool
	noAlt        bool
}

// defaultProfile returns AWS_PROFILE if set, otherwise empty so the AWS CLI
// uses its normal default (no --profile flag; same as running `aws` in your shell).
func defaultProfile() string {
	return strings.TrimSpace(os.Getenv("AWS_PROFILE"))
}

// defaultRegion returns the first of AWS_REGION, AWS_DEFAULT_REGION if set,
// otherwise empty so the CLI uses region from ~/.aws/config for the active profile.
func defaultRegion() string {
	for _, key := range []string{"AWS_REGION", "AWS_DEFAULT_REGION"} {
		if v := strings.TrimSpace(os.Getenv(key)); v != "" {
			return v
		}
	}
	return ""
}

func parseOptions() (options, error) {
	cfg, err := loadConfig()
	if err != nil {
		return options{}, err
	}

	opts := options{
		profile: defaultProfile(),
		region:  defaultRegion(),
		ttl:     cfg.CacheTTL,
	}

	flag.StringVar(&opts.profile, "profile", opts.profile, "AWS profile (required unless AWS_PROFILE is set)")
	flag.StringVar(&opts.profile, "p", opts.profile, "AWS profile (required unless AWS_PROFILE is set)")
	flag.StringVar(&opts.region, "region", opts.region, "AWS region (or set AWS_REGION / AWS_DEFAULT_REGION / aws configure)")
	flag.StringVar(&opts.region, "r", opts.region, "AWS region (or env / aws configure)")
	flag.StringVar(&opts.query, "query", "", "Initial filter query")
	flag.StringVar(&opts.query, "q", "", "Initial filter query")
	flag.BoolVar(&opts.forceRefresh, "force-refresh", false, "Ignore a valid cache and refetch instances")
	flag.BoolVar(&opts.forceRefresh, "f", false, "Ignore a valid cache and refetch instances")
	flag.IntVar(&opts.ttl, "ttl", opts.ttl, "Cache TTL in seconds")
	flag.IntVar(&opts.ttl, "t", opts.ttl, "Cache TTL in seconds")
	flag.BoolVar(&opts.debug, "debug", false, "Enable debug output")
	flag.BoolVar(&opts.debug, "d", false, "Enable debug output")
	flag.BoolVar(&opts.noAlt, "no-alt", false, "Run without alternate screen mode")
	flag.Parse()

	if opts.ttl < 0 {
		return options{}, fmt.Errorf("ttl must be >= 0")
	}

	return opts, nil
}

// resolveRegionFromAWSConfig fills opts.region from `aws configure get region` when env/flags left it empty.
func resolveRegionFromAWSConfig(opts *options) {
	if strings.TrimSpace(opts.region) != "" {
		return
	}
	args := make([]string, 0, 6)
	if p := strings.TrimSpace(opts.profile); p != "" {
		args = append(args, "--profile", p)
	}
	args = append(args, "configure", "get", "region")
	out, err := exec.Command("aws", args...).Output()
	if err != nil {
		return
	}
	if r := strings.TrimSpace(string(out)); r != "" {
		opts.region = r
	}
}

func validateAWSContext(opts *options) error {
	if strings.TrimSpace(opts.profile) == "" {
		return fmt.Errorf("AWS profile is not set — set AWS_PROFILE or use --profile (e.g. --profile default for the default profile)")
	}
	if strings.TrimSpace(opts.region) == "" {
		return fmt.Errorf("AWS region is not set — set AWS_REGION or AWS_DEFAULT_REGION, use --region, or run aws configure (region for profile %q)", opts.profile)
	}
	return nil
}

func main() {
	opts, err := parseOptions()
	if err != nil {
		fmt.Fprintf(os.Stderr, "error: %v\n", err)
		os.Exit(1)
	}

	if err := ensureAWSCLI(); err != nil {
		fmt.Fprintf(os.Stderr, "error: %v\n", err)
		os.Exit(1)
	}

	resolveRegionFromAWSConfig(&opts)
	if err := validateAWSContext(&opts); err != nil {
		fmt.Fprintf(os.Stderr, "ssm-connect: %v\n", err)
		os.Exit(1)
	}

	model, err := newModel(opts)
	if err != nil {
		fmt.Fprintf(os.Stderr, "error: %v\n", err)
		os.Exit(1)
	}

	programOpts := []tea.ProgramOption{}
	p := tea.NewProgram(model, programOpts...)
	if _, err := p.Run(); err != nil {
		fmt.Fprintf(os.Stderr, "error: %v\n", err)
		os.Exit(1)
	}
}
