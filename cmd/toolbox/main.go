// Command toolbox installs CLI tools and manages shell module config.
package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

func main() {
	if err := run(); err != nil {
		fmt.Fprintf(os.Stderr, "toolbox: %v\n", err)
		os.Exit(1)
	}
}

func run() error {
	args := os.Args[1:]
	if len(args) == 0 {
		usage()
		return nil
	}
	switch args[0] {
	case "help", "-h", "--help":
		usage()
		return nil
	case "install":
		return installTools(toolboxRoot())
	case "clean":
		return cleanTools(toolboxRoot())
	case "list":
		return listTools(toolboxRoot())
	case "shell":
		return runShell(args[1:])
	case "deps":
		return runDeps(args[1:])
	case "bootstrap":
		return runBootstrap(args[1:])
	default:
		return fmt.Errorf("unknown command %q — run 'toolbox help'", args[0])
	}
}

func usage() {
	root := toolboxRoot()
	fmt.Printf(`Toolbox - Personal CLI tool manager

Usage: toolbox <command> [arguments]

Commands:
  install    Symlink scripts, compile Swift, build Go CLIs into bin/
  clean      Remove dead symlinks from bin/
  list       List commands in bin/
  shell      Shell module config (see below)
  deps scan  Print advisory list of command -v tokens from shell scripts
  bootstrap linux-install         Auto-install packages via paru/pacman/apt/dnf; falls back to linux-print
  bootstrap linux-print           Print Linux checklists + apt/dnf paste lines
  bootstrap brew-bundle [flags]  Write a temp Brewfile from deps YAML; print brew bundle sample command
                                   Flags: --only=toolbox|tools|all (default all), --path-only (stdout = Brewfile path)
  help       Show this message

Shell:
  toolbox shell path                    Print path to shell.yaml
  toolbox shell list                    List modules with enabled/disabled source, overrides, and runtime status
  toolbox shell disable <stem> [...]    Add stems to disabled_modules in shell.yaml
  toolbox shell enable <stem> [...]     Remove stems from disabled_modules
  toolbox shell effective               Internal: print final disabled stems (one per line)

Effective disabled set = file disabled_modules
  plus comma-separated TOOLBOX_SHELL_DISABLED
  minus comma-separated TOOLBOX_SHELL_ENABLED

Environment:
  TOOLBOX_ROOT          Repository root (default: inferred from binary location)

Paths:
  Root:     %s
  Bin:      %s
  Scripts:  %s
`, root, filepath.Join(root, "bin"), filepath.Join(root, "scripts"))
}

func toolboxRoot() string {
	if e := os.Getenv("TOOLBOX_ROOT"); e != "" {
		return filepath.Clean(e)
	}
	exe, err := os.Executable()
	if err == nil {
		exe, _ = filepath.EvalSymlinks(exe)
		dir := filepath.Dir(exe)
		if filepath.Base(dir) == "bin" {
			return filepath.Clean(filepath.Join(dir, ".."))
		}
	}
	wd, _ := os.Getwd()
	return wd
}

func runShell(args []string) error {
	if len(args) == 0 {
		return fmt.Errorf("shell: need a subcommand (path, effective, list, disable, enable)")
	}
	root := toolboxRoot()
	switch args[0] {
	case "path":
		p, err := shellConfigPath()
		if err != nil {
			return err
		}
		fmt.Println(p)
		return nil
	case "effective":
		cfg, _, err := loadShellConfig()
		if err != nil {
			return err
		}
		for _, s := range effectiveDisabledList(cfg) {
			fmt.Println(s)
		}
		return nil
	case "list":
		return shellList(root)
	case "disable":
		if len(args) < 2 {
			return fmt.Errorf("shell disable: need at least one stem")
		}
		stems := args[1:]
		if err := validateModuleStems(root, stems); err != nil {
			return err
		}
		cfg, _, err := loadShellConfig()
		if err != nil {
			return err
		}
		return addDisabledModules(cfg, stems...)
	case "enable":
		if len(args) < 2 {
			return fmt.Errorf("shell enable: need at least one stem")
		}
		stems := args[1:]
		cfg, _, err := loadShellConfig()
		if err != nil {
			return err
		}
		return removeDisabledModules(cfg, stems...)
	default:
		return fmt.Errorf("shell: unknown subcommand %q", args[0])
	}
}

func shellList(root string) error {
	mods, err := moduleStems(root)
	if err != nil {
		return err
	}
	cfg, path, err := loadShellConfig()
	if err != nil {
		return err
	}
	eff := effectiveDisabled(cfg)
	fileDisabled := configDisabledSet(cfg)
	envDisabled := parseCSVSet(os.Getenv("TOOLBOX_SHELL_DISABLED"))
	envEnabled := parseCSVSet(os.Getenv("TOOLBOX_SHELL_ENABLED"))
	active := parseCSVSet(os.Getenv("TOOLBOX_SHELL_ACTIVE"))
	unavailable := parseUnavailableMap(os.Getenv("TOOLBOX_SHELL_UNAVAILABLE"))
	fmt.Printf("shell.yaml: %s\n", path)
	fmt.Printf("defaults come from shell.yaml disabled_modules.\n")
	fmt.Printf("session overrides: TOOLBOX_SHELL_DISABLED adds disables; TOOLBOX_SHELL_ENABLED re-enables and wins.\n\n")
	fmt.Printf("%-12s %-9s %-14s %-10s %-12s %s\n", "STEM", "ENABLED", "DEFAULT", "OVERRIDE", "RUNTIME", "WHY")
	for _, m := range mods {
		enabled := "yes"
		defaultSource := "-"
		override := "-"
		runtime := "loaded"
		reason := ""
		if _, ok := fileDisabled[m]; ok {
			defaultSource = "shell.yaml"
		}
		if _, ok := envDisabled[m]; ok {
			override = "disabled"
		}
		if _, ok := envEnabled[m]; ok {
			override = "enabled"
		}
		if _, dis := eff[m]; dis {
			enabled = "no"
			runtime = "disabled"
		} else if why, ok := unavailable[m]; ok {
			runtime = "unavailable"
			reason = why
		} else if _, ok := active[m]; ok {
			runtime = "active"
		}
		fmt.Printf("%-12s %-9s %-14s %-10s %-12s %s\n", m, enabled, defaultSource, override, runtime, reason)
	}
	return nil
}

func configDisabledSet(cfg *shellConfig) map[string]struct{} {
	out := make(map[string]struct{})
	for _, s := range cfg.DisabledModules {
		s = strings.TrimSpace(s)
		if s != "" {
			out[s] = struct{}{}
		}
	}
	return out
}

func parseCSVSet(s string) map[string]struct{} {
	out := make(map[string]struct{})
	for _, part := range strings.Split(s, ",") {
		part = strings.TrimSpace(part)
		if part != "" {
			out[part] = struct{}{}
		}
	}
	return out
}

func parseUnavailableMap(s string) map[string]string {
	out := make(map[string]string)
	for _, part := range strings.Split(s, ";") {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		key, value, ok := strings.Cut(part, "=")
		if !ok {
			continue
		}
		key = strings.TrimSpace(key)
		value = strings.TrimSpace(value)
		if key != "" {
			out[key] = value
		}
	}
	return out
}

func runDeps(args []string) error {
	if len(args) == 0 || args[0] != "scan" {
		return fmt.Errorf("deps: use 'toolbox deps scan'")
	}
	return scanScripts(toolboxRoot())
}
