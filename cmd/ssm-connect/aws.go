package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"slices"
	"strings"
	"time"
)

type Instance struct {
	Name          string `json:"name"`
	InstanceID    string `json:"instance_id"`
	PrivateIP     string `json:"private_ip"`
	PublicIP      string `json:"public_ip"`
	State         string `json:"state"`
	ImageID       string `json:"image_id"`
	InstanceType  string `json:"instance_type"`
	Platform      string `json:"platform"`
	KeyName       string `json:"key_name"`
	PublicDNSName string `json:"public_dns_name"`
}

// SSMInstanceInfo is a subset of AWS SSM describe-instance-information fields.
type SSMInstanceInfo struct {
	InstanceID    string `json:"InstanceId"`
	PingStatus    string `json:"PingStatus"`
	PlatformType  string `json:"PlatformType"`
	PlatformName  string `json:"PlatformName"`
	AgentVersion  string `json:"AgentVersion"`
}

type describeInstanceInformationPage struct {
	InstanceInformationList []SSMInstanceInfo `json:"InstanceInformationList"`
	NextToken               string            `json:"NextToken"`
}

func describeSSMChunk(profile, region string, ids []string) (map[string]SSMInstanceInfo, error) {
	if len(ids) == 0 {
		return map[string]SSMInstanceInfo{}, nil
	}
	filter := "Key=InstanceIds,Values=" + strings.Join(ids, ",")
	cmd := exec.Command("aws", awsArgs(profile, region,
		"ssm", "describe-instance-information", "--output", "json", "--filters", filter)...)
	output, err := cmd.Output()
	if err != nil {
		return nil, commandError("describe-instance-information (filtered)", err)
	}
	var page describeInstanceInformationPage
	if err := json.Unmarshal(output, &page); err != nil {
		return nil, fmt.Errorf("parse SSM response: %w", err)
	}
	out := make(map[string]SSMInstanceInfo, len(page.InstanceInformationList))
	for _, row := range page.InstanceInformationList {
		if row.InstanceID != "" {
			out[row.InstanceID] = row
		}
	}
	return out, nil
}

func fetchSSMPaginatedFilter(profile, region string, want map[string]struct{}) (map[string]SSMInstanceInfo, error) {
	out := make(map[string]SSMInstanceInfo)
	if len(want) == 0 {
		return out, nil
	}
	var token string
	for {
		args := awsArgs(profile, region, "ssm", "describe-instance-information", "--output", "json", "--max-results", "50")
		if token != "" {
			args = append(args, "--starting-token", token)
		}
		cmd := exec.Command("aws", args...)
		output, err := cmd.Output()
		if err != nil {
			return out, commandError("describe-instance-information", err)
		}
		var page describeInstanceInformationPage
		if err := json.Unmarshal(output, &page); err != nil {
			return out, fmt.Errorf("parse SSM response: %w", err)
		}
		for _, row := range page.InstanceInformationList {
			id := row.InstanceID
			if id == "" {
				continue
			}
			if _, ok := want[id]; ok {
				out[id] = row
			}
		}
		if page.NextToken == "" {
			break
		}
		token = page.NextToken
		if len(out) >= len(want) {
			break
		}
	}
	return out, nil
}

func fetchSSMInstanceInformation(profile, region string, ids []string) (map[string]SSMInstanceInfo, error) {
	if len(ids) == 0 {
		return map[string]SSMInstanceInfo{}, nil
	}
	want := make(map[string]struct{}, len(ids))
	cleanIDs := make([]string, 0, len(ids))
	for _, id := range ids {
		id = strings.TrimSpace(id)
		if id == "" {
			continue
		}
		if _, seen := want[id]; seen {
			continue
		}
		want[id] = struct{}{}
		cleanIDs = append(cleanIDs, id)
	}
	if len(cleanIDs) == 0 {
		return map[string]SSMInstanceInfo{}, nil
	}

	const chunkSize = 50
	merged := make(map[string]SSMInstanceInfo)
	for i := 0; i < len(cleanIDs); i += chunkSize {
		end := i + chunkSize
		if end > len(cleanIDs) {
			end = len(cleanIDs)
		}
		chunk := cleanIDs[i:end]
		part, err := describeSSMChunk(profile, region, chunk)
		if err != nil {
			return fetchSSMPaginatedFilter(profile, region, want)
		}
		for k, v := range part {
			merged[k] = v
		}
	}
	return merged, nil
}

func (i Instance) title() string {
	name := i.Name
	if name == "" {
		name = "<unnamed>"
	}
	return fmt.Sprintf("%s  %s", i.InstanceID, name)
}

type cacheEnvelope struct {
	GeneratedAt time.Time  `json:"generated_at"`
	Instances   []Instance `json:"instances"`
}

type describeInstancesOutput struct {
	Reservations []struct {
		Instances []struct {
			InstanceID     string `json:"InstanceId"`
			PrivateIP      string `json:"PrivateIpAddress"`
			PublicIP       string `json:"PublicIpAddress"`
			ImageID        string `json:"ImageId"`
			InstanceType   string `json:"InstanceType"`
			PublicDNSName  string `json:"PublicDnsName"`
			KeyName        string `json:"KeyName"`
			Platform       string `json:"Platform"`
			PlatformDetail string `json:"PlatformDetails"`
			State          struct {
				Name string `json:"Name"`
			} `json:"State"`
			Tags []struct {
				Key   string `json:"Key"`
				Value string `json:"Value"`
			} `json:"Tags"`
		} `json:"Instances"`
	} `json:"Reservations"`
}

func ensureAWSCLI() error {
	if _, err := exec.LookPath("aws"); err != nil {
		return fmt.Errorf("aws CLI is required")
	}
	return nil
}

func awsArgs(profile, region string, extra ...string) []string {
	args := make([]string, 0, 4+len(extra))
	if profile != "" {
		args = append(args, "--profile", profile)
	}
	if region != "" {
		args = append(args, "--region", region)
	}
	args = append(args, extra...)
	return args
}

func fetchInstances(profile, region string) ([]Instance, error) {
	cmd := exec.Command("aws", awsArgs(profile, region, "ec2", "describe-instances", "--output", "json")...)
	output, err := cmd.Output()
	if err != nil {
		return nil, commandError("describe instances", err)
	}

	var response describeInstancesOutput
	if err := json.Unmarshal(output, &response); err != nil {
		return nil, fmt.Errorf("parse EC2 response: %w", err)
	}

	instances := make([]Instance, 0)
	for _, reservation := range response.Reservations {
		for _, inst := range reservation.Instances {
			name := ""
			for _, tag := range inst.Tags {
				if tag.Key == "Name" {
					name = tag.Value
					break
				}
			}

			platform := inst.PlatformDetail
			if platform == "" {
				platform = inst.Platform
			}

			instances = append(instances, Instance{
				Name:          name,
				InstanceID:    inst.InstanceID,
				PrivateIP:     inst.PrivateIP,
				PublicIP:      inst.PublicIP,
				State:         inst.State.Name,
				ImageID:       inst.ImageID,
				InstanceType:  inst.InstanceType,
				Platform:      platform,
				KeyName:       inst.KeyName,
				PublicDNSName: inst.PublicDNSName,
			})
		}
	}

	slices.SortFunc(instances, func(a, b Instance) int {
		if cmp := strings.Compare(strings.ToLower(a.Name), strings.ToLower(b.Name)); cmp != 0 {
			if a.Name == "" {
				return 1
			}
			if b.Name == "" {
				return -1
			}
			return cmp
		}
		return strings.Compare(a.InstanceID, b.InstanceID)
	})

	return instances, nil
}

func runSession(profile, region, instanceID string) *exec.Cmd {
	args := awsArgs(profile, region, "ssm", "start-session", "--target", instanceID)
	cmd := exec.Command("aws", args...)
	cmd.Stdin = os.Stdin
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	return cmd
}

func commandError(action string, err error) error {
	var exitErr *exec.ExitError
	if errors.As(err, &exitErr) {
		msg := strings.TrimSpace(string(exitErr.Stderr))
		if msg != "" {
			return fmt.Errorf("%s: %s", action, msg)
		}
	}
	return fmt.Errorf("%s: %w", action, err)
}

func loadCachedInstances(path string) ([]Instance, time.Time, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, time.Time{}, err
	}

	var envelope cacheEnvelope
	if err := json.Unmarshal(data, &envelope); err != nil {
		return nil, time.Time{}, fmt.Errorf("parse cache: %w", err)
	}
	return envelope.Instances, envelope.GeneratedAt, nil
}

func writeCachedInstances(path string, instances []Instance) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o750); err != nil {
		return fmt.Errorf("create cache dir: %w", err)
	}

	envelope := cacheEnvelope{
		GeneratedAt: time.Now(),
		Instances:   instances,
	}

	data, err := json.MarshalIndent(envelope, "", "  ")
	if err != nil {
		return fmt.Errorf("encode cache: %w", err)
	}

	if err := os.WriteFile(path, data, 0o600); err != nil {
		return fmt.Errorf("write cache: %w", err)
	}
	return nil
}

func cacheExpired(path string, ttl int) bool {
	if ttl == 0 {
		return true
	}

	info, err := os.Stat(path)
	if err != nil {
		return true
	}
	return time.Since(info.ModTime()) > time.Duration(ttl)*time.Second
}
