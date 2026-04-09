package main

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
)

var reCommandV = regexp.MustCompile(`command\s+(?:-v|--version)\s+([a-zA-Z0-9_.+-]+)`)
var reWhich = regexp.MustCompile(`\$\(which\s+([a-zA-Z0-9_.+-]+)`)

// scanScripts walks scripts/**/*.sh under root and prints unique tokens (stderr notes).
func scanScripts(root string) error {
	scriptsDir := filepath.Join(root, "scripts")
	found := make(map[string]struct{})
	err := filepath.WalkDir(scriptsDir, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			return nil
		}
		if filepath.Ext(path) != ".sh" {
			return nil
		}
		f, err := os.Open(path)
		if err != nil {
			return nil
		}
		defer f.Close()
		sc := bufio.NewScanner(f)
		for sc.Scan() {
			line := sc.Text()
			for _, m := range reCommandV.FindAllStringSubmatch(line, -1) {
				if len(m) > 1 {
					found[m[1]] = struct{}{}
				}
			}
			for _, m := range reWhich.FindAllStringSubmatch(line, -1) {
				if len(m) > 1 {
					found[m[1]] = struct{}{}
				}
			}
		}
		return sc.Err()
	})
	if err != nil && !os.IsNotExist(err) {
		return err
	}
	var names []string
	for s := range found {
		names = append(names, s)
	}
	sort.Strings(names)
	fmt.Println("# Advisory: commands seen via command -v / $(which ...) in scripts/**/*.sh")
	fmt.Println("# Merge into deps/toolbox.yaml manually if appropriate.")
	for _, s := range names {
		fmt.Println(s)
	}
	return nil
}
