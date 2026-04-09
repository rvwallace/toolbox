package main

import (
	"fmt"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

// installTools symlinks scripts, compiles Swift, builds Go CLIs under cmd/*.
func installTools(root string) error {
	binDir := filepath.Join(root, "bin")
	scriptsDir := filepath.Join(root, "scripts")
	cmdDir := filepath.Join(root, "cmd")
	goCommands, err := discoverGoCommands(cmdDir)
	if err != nil {
		return err
	}

	if err := os.MkdirAll(binDir, 0o755); err != nil {
		return err
	}

	cleaned, err := cleanDeadSymlinks(binDir)
	if err != nil {
		return err
	}
	if cleaned > 0 {
		fmt.Printf("  cleaned %d dead symlink(s)\n", cleaned)
	}

	count := 0

	if st, err := os.Stat(scriptsDir); err == nil && st.IsDir() {
		if err := filepath.WalkDir(scriptsDir, func(path string, d fs.DirEntry, err error) error {
			if err != nil {
				return err
			}
			if d.IsDir() {
				return nil
			}
			ext := strings.ToLower(filepath.Ext(path))
			if ext != ".py" && ext != ".sh" {
				return nil
			}
			base := filepath.Base(path)
			name := strings.TrimSuffix(base, ext)
			if goCommands[name] {
				return nil
			}
			platforms, err := readScriptPlatforms(path)
			if err != nil {
				return fmt.Errorf("%s: %w", path, err)
			}
			supported, err := isPlatformSupported(platforms)
			if err != nil {
				return fmt.Errorf("%s: %w", path, err)
			}
			rel := filepath.Join("..", "scripts", strings.TrimPrefix(path, scriptsDir+string(filepath.Separator)))
			rel = filepath.ToSlash(rel)
			target := filepath.Join(binDir, name)
			if !supported {
				if err := removeBinTarget(target); err != nil {
					return err
				}
				fmt.Printf("  skip: %s (platforms: %s)\n", name, platformSummary(platforms))
				return nil
			}

			if fi, err := os.Lstat(target); err == nil {
				if fi.Mode()&fs.ModeSymlink != 0 {
					cur, _ := os.Readlink(target)
					if cur == rel {
						fmt.Printf("  link: %s -> %s\n", name, rel)
						count++
						return nil
					}
					_ = os.Remove(target)
				} else {
					fmt.Printf("  skip: %s (exists and is not a symlink)\n", name)
					return nil
				}
			}

			if err := os.Symlink(rel, target); err != nil {
				return err
			}
			fmt.Printf("  link: %s -> %s\n", name, rel)
			count++
			return nil
		}); err != nil {
			return err
		}
	} else if err != nil && !os.IsNotExist(err) {
		return err
	}

	swiftcPath, haveSwiftc := "", false
	if p, err := exec.LookPath("swiftc"); err == nil {
		swiftcPath = p
		haveSwiftc = true
	}
	if _, err := os.Stat(scriptsDir); err == nil {
		if err := filepath.WalkDir(scriptsDir, func(path string, d fs.DirEntry, err error) error {
			if err != nil {
				return err
			}
			if d.IsDir() {
				return nil
			}
			if strings.ToLower(filepath.Ext(path)) != ".swift" {
				return nil
			}
			base := filepath.Base(path)
			name := strings.TrimSuffix(base, ".swift")
			out := filepath.Join(binDir, name)
			platforms, err := readScriptPlatforms(path)
			if err != nil {
				return fmt.Errorf("%s: %w", path, err)
			}
			supported, err := isPlatformSupported(platforms)
			if err != nil {
				return fmt.Errorf("%s: %w", path, err)
			}
			if !supported {
				if err := removeBinTarget(out); err != nil {
					return err
				}
				fmt.Printf("  skip: %s (platforms: %s)\n", name, platformSummary(platforms))
				return nil
			}
			if !haveSwiftc {
				return nil
			}
			if st, err := os.Stat(out); err == nil {
				srcSt, err := os.Stat(path)
				if err == nil && st.ModTime().After(srcSt.ModTime()) {
					return nil
				}
			}
			fmt.Printf("  build: %s (swift)\n", name)
			cmd := exec.Command(swiftcPath, "-O", "-o", out, path)
			cmd.Stderr = os.Stderr
			if err := cmd.Run(); err != nil {
				fmt.Printf("  error: failed to compile %s\n", name)
				return nil
			}
			count++
			return nil
		}); err != nil {
			return err
		}
	} else if err != nil && !os.IsNotExist(err) {
		return err
	}

	if _, err := exec.LookPath("go"); err == nil {
		entries, err := os.ReadDir(cmdDir)
		if err == nil {
			for _, e := range entries {
				if !e.IsDir() {
					continue
				}
				name := e.Name()
				sub := filepath.Join(cmdDir, name)
				if _, err := os.Stat(filepath.Join(sub, "main.go")); err != nil {
					continue
				}
				platforms, err := readCommandPlatforms(sub)
				if err != nil {
					return err
				}
				supported, err := isPlatformSupported(platforms)
				if err != nil {
					return fmt.Errorf("%s: %w", sub, err)
				}
				out := filepath.Join(binDir, name)
				if !supported {
					if err := removeBinTarget(out); err != nil {
						return err
					}
					fmt.Printf("  skip: %s (platforms: %s)\n", name, platformSummary(platforms))
					continue
				}
				if fi, err := os.Lstat(out); err == nil && fi.Mode()&fs.ModeSymlink != 0 {
					if err := os.Remove(out); err != nil {
						return fmt.Errorf("remove stale symlink for %s: %w", name, err)
					}
				}
				fmt.Printf("  build: %s (go)\n", name)
				c := exec.Command("go", "build", "-o", out, ".")
				c.Dir = sub
				c.Stderr = os.Stderr
				if err := c.Run(); err != nil {
					return fmt.Errorf("go build %s: %w", name, err)
				}
				count++
			}
		}
	}

	fmt.Printf("Done. %d command(s) installed.\n", count)
	return nil
}

func discoverGoCommands(cmdDir string) (map[string]bool, error) {
	commands := make(map[string]bool)
	entries, err := os.ReadDir(cmdDir)
	if os.IsNotExist(err) {
		return commands, nil
	}
	if err != nil {
		return nil, err
	}

	for _, e := range entries {
		if !e.IsDir() {
			continue
		}
		if _, err := os.Stat(filepath.Join(cmdDir, e.Name(), "main.go")); err == nil {
			commands[e.Name()] = true
		}
	}

	return commands, nil
}

func cleanDeadSymlinks(binDir string) (int, error) {
	ents, err := os.ReadDir(binDir)
	if err != nil {
		if os.IsNotExist(err) {
			return 0, nil
		}
		return 0, err
	}
	n := 0
	for _, e := range ents {
		path := filepath.Join(binDir, e.Name())
		fi, err := os.Lstat(path)
		if err != nil {
			continue
		}
		if fi.Mode()&fs.ModeSymlink == 0 {
			continue
		}
		if _, err := os.Stat(path); err != nil {
			if os.IsNotExist(err) {
				_ = os.Remove(path)
				n++
			}
		}
	}
	return n, nil
}

// cleanTools removes broken symlinks in bin/.
func cleanTools(root string) error {
	binDir := filepath.Join(root, "bin")
	fmt.Printf("Cleaning dead symlinks in %s...\n", binDir)
	ents, err := os.ReadDir(binDir)
	if err != nil {
		if os.IsNotExist(err) {
			fmt.Println("Done. 0 dead symlink(s) removed.")
			return nil
		}
		return err
	}
	n := 0
	for _, e := range ents {
		path := filepath.Join(binDir, e.Name())
		fi, err := os.Lstat(path)
		if err != nil {
			continue
		}
		if fi.Mode()&fs.ModeSymlink == 0 {
			continue
		}
		if _, err := os.Stat(path); err != nil && os.IsNotExist(err) {
			fmt.Printf("  remove: %s\n", e.Name())
			_ = os.Remove(path)
			n++
		}
	}
	fmt.Printf("Done. %d dead symlink(s) removed.\n", n)
	return nil
}

// listTools prints bin/ contents with type hints.
func listTools(root string) error {
	binDir := filepath.Join(root, "bin")
	fmt.Printf("Available commands in %s:\n\n", binDir)
	ents, err := os.ReadDir(binDir)
	if err != nil || len(ents) == 0 {
		fmt.Println("  (none - run 'toolbox install' first)")
		return nil
	}
	for _, e := range ents {
		name := e.Name()
		path := filepath.Join(binDir, name)
		typ := "binary"
		if fi, err := os.Lstat(path); err == nil && fi.Mode()&fs.ModeSymlink != 0 {
			tgt, _ := os.Readlink(path)
			switch {
			case strings.HasSuffix(tgt, ".py"):
				typ = "python"
			case strings.HasSuffix(tgt, ".sh"):
				typ = "shell"
			case strings.HasSuffix(tgt, ".swift"):
				typ = "swift"
			}
		}
		fmt.Printf("  %-20s (%s)\n", name, typ)
	}
	return nil
}
