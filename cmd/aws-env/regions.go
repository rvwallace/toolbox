package main

import "fmt"

type region struct {
	Code string
	Desc string
}

var awsRegions = []region{
	{"us-east-1", "US East (N. Virginia)"},
	{"us-east-2", "US East (Ohio)"},
	{"us-west-1", "US West (N. California)"},
	{"us-west-2", "US West (Oregon)"},
	{"eu-west-1", "Europe (Ireland)"},
	{"eu-west-2", "Europe (London)"},
	{"eu-west-3", "Europe (Paris)"},
	{"eu-central-1", "Europe (Frankfurt)"},
	{"eu-central-2", "Europe (Zurich)"},
	{"eu-north-1", "Europe (Stockholm)"},
	{"eu-south-1", "Europe (Milan)"},
	{"eu-south-2", "Europe (Spain)"},
	{"ap-northeast-1", "Asia Pacific (Tokyo)"},
	{"ap-northeast-2", "Asia Pacific (Seoul)"},
	{"ap-northeast-3", "Asia Pacific (Osaka)"},
	{"ap-southeast-1", "Asia Pacific (Singapore)"},
	{"ap-southeast-2", "Asia Pacific (Sydney)"},
	{"ap-southeast-3", "Asia Pacific (Jakarta)"},
	{"ap-southeast-4", "Asia Pacific (Melbourne)"},
	{"ap-south-1", "Asia Pacific (Mumbai)"},
	{"ap-south-2", "Asia Pacific (Hyderabad)"},
	{"ap-east-1", "Asia Pacific (Hong Kong)"},
	{"sa-east-1", "South America (São Paulo)"},
	{"ca-central-1", "Canada (Central)"},
	{"ca-west-1", "Canada (Calgary)"},
	{"af-south-1", "Africa (Cape Town)"},
	{"me-south-1", "Middle East (Bahrain)"},
	{"me-central-1", "Middle East (UAE)"},
}

func regionDisplayItems() []string {
	items := make([]string, len(awsRegions))
	for i, r := range awsRegions {
		items[i] = fmt.Sprintf("%-20s %s", r.Code, r.Desc)
	}
	return items
}

func regionCode(item string) string {
	// item is "us-east-1            US East (N. Virginia)"
	for _, r := range awsRegions {
		if len(item) >= len(r.Code) && item[:len(r.Code)] == r.Code {
			return r.Code
		}
	}
	// fallback: first word
	for i, c := range item {
		if c == ' ' {
			return item[:i]
		}
	}
	return item
}
