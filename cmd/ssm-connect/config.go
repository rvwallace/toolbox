package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
)

type Config struct {
	CacheTTL int `json:"cache_ttl"`
}

func defaultConfig() Config {
	return Config{
		CacheTTL: 86400,
	}
}

func xdgConfigBase() (string, error) {
	base := os.Getenv("XDG_CONFIG_HOME")
	if base != "" {
		return base, nil
	}

	home, err := os.UserHomeDir()
	if err != nil {
		return "", fmt.Errorf("find home dir: %w", err)
	}
	return filepath.Join(home, ".config"), nil
}

func xdgCacheBase() (string, error) {
	base := os.Getenv("XDG_CACHE_HOME")
	if base != "" {
		return base, nil
	}

	home, err := os.UserHomeDir()
	if err != nil {
		return "", fmt.Errorf("find home dir: %w", err)
	}
	return filepath.Join(home, ".cache"), nil
}

func configPath() (string, error) {
	base, err := xdgConfigBase()
	if err != nil {
		return "", err
	}
	return filepath.Join(base, "silentcastle", "ssm-connect.json"), nil
}

func cacheDir() (string, error) {
	base, err := xdgCacheBase()
	if err != nil {
		return "", err
	}
	return filepath.Join(base, "silentcastle"), nil
}

func cachePath(profile, region string) (string, error) {
	base, err := cacheDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(base, fmt.Sprintf("ssm-connect-%s-%s.json", profile, region)), nil
}

// pythonCacheTTL is the shape written by scripts/aws/ssm-connect.py (ssm-connect.json).
type pythonCacheTTL struct {
	Value int `json:"value"`
}

func cacheTTLFromRawMessage(raw json.RawMessage, fallback int) int {
	if len(raw) == 0 {
		return fallback
	}
	var n int
	if err := json.Unmarshal(raw, &n); err == nil && n > 0 {
		return n
	}
	var wrap pythonCacheTTL
	if err := json.Unmarshal(raw, &wrap); err == nil && wrap.Value > 0 {
		return wrap.Value
	}
	return fallback
}

func loadConfig() (Config, error) {
	path, err := configPath()
	if err != nil {
		return defaultConfig(), err
	}

	data, err := os.ReadFile(path)
	if os.IsNotExist(err) {
		return defaultConfig(), nil
	}
	if err != nil {
		return defaultConfig(), fmt.Errorf("read config: %w", err)
	}

	def := defaultConfig()
	cfg := def

	var raw map[string]json.RawMessage
	if err := json.Unmarshal(data, &raw); err != nil {
		// Not a JSON object (e.g. truncated file); fall back to struct-only parse for slim configs.
		if err2 := json.Unmarshal(data, &cfg); err2 != nil {
			return def, fmt.Errorf("parse config: %w", err)
		}
		if cfg.CacheTTL < 0 {
			cfg.CacheTTL = def.CacheTTL
		}
		return cfg, nil
	}

	// Python ssm-connect.json uses CACHE_TTL: { "value": 86400, ... }
	if v, ok := raw["CACHE_TTL"]; ok {
		cfg.CacheTTL = cacheTTLFromRawMessage(v, cfg.CacheTTL)
	}
	// Go-native slim config: { "cache_ttl": 86400 }
	if v, ok := raw["cache_ttl"]; ok {
		cfg.CacheTTL = cacheTTLFromRawMessage(v, cfg.CacheTTL)
	}
	if cfg.CacheTTL < 0 {
		cfg.CacheTTL = def.CacheTTL
	}
	return cfg, nil
}
