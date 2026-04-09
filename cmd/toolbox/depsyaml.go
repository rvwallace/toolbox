package main

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"gopkg.in/yaml.v3"
)

// depsFile describes one deps YAML file.
type depsFile struct {
	Brew           []string   `yaml:"brew"`
	AptPackages    []string   `yaml:"apt_packages"`
	DnfPackages    []string   `yaml:"dnf_packages"`
	PacmanPackages []string   `yaml:"pacman_packages"`
	Descriptions   []depsItem `yaml:"items"`
}

// depsItem is an optional per-tool row with different package-manager names.
type depsItem struct {
	Name   string `yaml:"name"`
	Brew   string `yaml:"brew"`
	Apt    string `yaml:"apt"`
	Dnf    string `yaml:"dnf"`
	Pacman string `yaml:"pacman"`
}

// loadDepsFile reads path; missing file returns an empty config.
func loadDepsFile(root, rel string) (*depsFile, error) {
	p := filepath.Join(root, rel)
	data, err := os.ReadFile(p)
	if err != nil {
		if os.IsNotExist(err) {
			return &depsFile{}, nil
		}
		return nil, err
	}
	var f depsFile
	if err := yaml.Unmarshal(data, &f); err != nil {
		return nil, err
	}
	f.mergeItemsIntoLists()
	return &f, nil
}

func (f *depsFile) mergeItemsIntoLists() {
	for _, it := range f.Descriptions {
		if it.Brew != "" {
			f.Brew = append(f.Brew, it.Brew)
		} else if it.Name != "" {
			f.Brew = append(f.Brew, it.Name)
		}
		if it.Apt != "" {
			f.AptPackages = append(f.AptPackages, it.Apt)
		}
		if it.Dnf != "" {
			f.DnfPackages = append(f.DnfPackages, it.Dnf)
		}
		if it.Pacman != "" {
			f.PacmanPackages = append(f.PacmanPackages, it.Pacman)
		}
	}
	f.Brew = dedupeStrings(f.Brew)
	f.AptPackages = dedupeStrings(f.AptPackages)
	f.DnfPackages = dedupeStrings(f.DnfPackages)
	f.PacmanPackages = dedupeStrings(f.PacmanPackages)
}

func dedupeStrings(s []string) []string {
	seen := make(map[string]struct{})
	var out []string
	for _, x := range s {
		x = strings.TrimSpace(x)
		if x == "" {
			continue
		}
		if _, ok := seen[x]; ok {
			continue
		}
		seen[x] = struct{}{}
		out = append(out, x)
	}
	sort.Strings(out)
	return out
}

// joinShellPackages returns a space-separated string for apt/dnf install.
func joinShellPackages(pkgs []string) string {
	return strings.Join(pkgs, " ")
}

// brewFormulas returns brew names from deps YAML for only:
// "toolbox" (deps/toolbox.yaml), "tools" (deps/tools.yaml), or "all" (merged, deduped).
func brewFormulas(root, only string) ([]string, error) {
	switch only {
	case "toolbox":
		f, err := loadDepsFile(root, "deps/toolbox.yaml")
		if err != nil {
			return nil, err
		}
		return f.Brew, nil
	case "tools":
		f, err := loadDepsFile(root, "deps/tools.yaml")
		if err != nil {
			return nil, err
		}
		return f.Brew, nil
	case "all":
		a, err := loadDepsFile(root, "deps/toolbox.yaml")
		if err != nil {
			return nil, err
		}
		b, err := loadDepsFile(root, "deps/tools.yaml")
		if err != nil {
			return nil, err
		}
		return dedupeStrings(append(append([]string{}, a.Brew...), b.Brew...)), nil
	default:
		return nil, fmt.Errorf("only must be toolbox, tools, or all, got %q", only)
	}
}
