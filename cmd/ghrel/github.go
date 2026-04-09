package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"time"
)

// Release maps to one entry from the GitHub releases API.
type Release struct {
	TagName     string  `json:"tag_name"`
	Name        string  `json:"name"`
	PublishedAt string  `json:"published_at"` // RFC3339, e.g. "2026-02-23T14:00:00Z"
	Assets      []Asset `json:"assets"`
}

// Asset is one downloadable file attached to a release.
type Asset struct {
	Name               string `json:"name"`
	BrowserDownloadURL string `json:"browser_download_url"`
	Size               int64  `json:"size"`
}

// githubClient wraps an http.Client and optional auth token.
type githubClient struct {
	http  *http.Client
	token string
}

// newGithubClient builds a client, picking up a token from the environment
// if set. Unauthenticated requests are allowed for public repos (60 req/hour).
// Set one of the following env vars for private repos or to raise the rate
// limit to 5000/hour. Priority order:
//
//	DRA_GITHUB_TOKEN → GITHUB_TOKEN → GH_TOKEN
func newGithubClient() *githubClient {
	var token string
	for _, env := range []string{"DRA_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"} {
		if v := os.Getenv(env); v != "" {
			token = v
			break
		}
	}

	return &githubClient{
		http:  &http.Client{Timeout: 15 * time.Second},
		token: token,
	}
}

// get performs an authenticated GET and decodes the JSON body into dst.
func (c *githubClient) get(url string, dst any) error {
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return fmt.Errorf("building request: %w", err)
	}

	req.Header.Set("Accept", "application/vnd.github+json")
	req.Header.Set("X-GitHub-Api-Version", "2022-11-28")
	if c.token != "" {
		req.Header.Set("Authorization", "Bearer "+c.token)
	}

	resp, err := c.http.Do(req)
	if err != nil {
		return fmt.Errorf("http get: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("github api returned %s", resp.Status)
	}

	if err := json.NewDecoder(resp.Body).Decode(dst); err != nil {
		return fmt.Errorf("decoding response: %w", err)
	}

	return nil
}

// fetchReleases returns up to perPage releases for the given "owner/repo" slug.
func (c *githubClient) fetchReleases(repo string, perPage int) ([]Release, error) {
	if perPage < 1 || perPage > 100 {
		perPage = 10
	}
	url := fmt.Sprintf("https://api.github.com/repos/%s/releases?per_page=%d", repo, perPage)
	var releases []Release
	if err := c.get(url, &releases); err != nil {
		return nil, err
	}
	return releases, nil
}
