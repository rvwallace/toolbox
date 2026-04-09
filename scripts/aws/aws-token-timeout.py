#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
# ]
# ///

import os
import re
from datetime import datetime
import argparse
from pathlib import Path
import sys

def parse_credentials_file(profile, credentials_file):
    """Parse AWS credentials file and extract token expiration for given profile."""
    if not os.path.isfile(credentials_file):
        print("Error: AWS credentials file not found.")
        sys.exit(1)

    try:
        with open(credentials_file, 'r') as f:
            content = f.read()
        
        # Find the profile section and extract expiration
        profile_pattern = rf'\[{re.escape(profile)}\](.*?)(?=\[|$)'
        profile_match = re.search(profile_pattern, content, re.DOTALL)
        
        if not profile_match:
            return None
            
        profile_content = profile_match.group(1)
        expires_pattern = r'x_security_token_expires\s*=\s*(\S+)'
        expires_match = re.search(expires_pattern, profile_content)
        
        return expires_match.group(1) if expires_match else None
        
    except Exception as e:
        print(f"Error reading credentials file: {e}")
        sys.exit(1)

def calculate_remaining_time(expires):
    """Calculate remaining time until expiration."""
    if not expires:
        return 0, "00:00:00"
    
    try:
        # First try parsing with colons in timezone
        formats_to_try = [
            "%Y-%m-%dT%H%M%S%z",  # Format like "2024-11-05T172421-0600"
            "%Y-%m-%dT%H%M%S-%z", # Format like "2024-11-05T172421-06:00" with colon removed
            "%Y-%m-%dT%H:%M:%S%z" # Standard ISO format
        ]
        
        # Remove colon from timezone if present
        if len(expires) > 20 and expires[-3] == ':':
            expires = expires[:-3] + expires[-2:]
        
        expires_dt = None
        for fmt in formats_to_try:
            try:
                expires_dt = datetime.strptime(expires, fmt)
                break
            except ValueError:
                continue
                
        if expires_dt is None:
            raise ValueError(f"Could not parse time: {expires}")
            
        current_dt = datetime.now(expires_dt.tzinfo)
        
        # Calculate remaining time
        remaining_seconds = int((expires_dt - current_dt).total_seconds())
        
        # Format time
        hours, remainder = divmod(abs(remaining_seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        formatted_time = f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"
        
        if remaining_seconds < 0:
            formatted_time = f"-{formatted_time}"
            
        return remaining_seconds, formatted_time
        
    except Exception as e:
        print(f"Error calculating remaining time: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description="Check AWS token expiration time.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s            # Show formatted output
  > Remaining: 02:20:43
  %(prog)s -f         # Show formatted output (default)
  > Remaining: 02:20:43
  %(prog)s -s         # Show remaining seconds
  > 8143
  %(prog)s -t         # Show remaining time
  > 02:20:43
        """
    )
    parser.add_argument('-f', action='store_true', help='Show formatted output (default)')
    parser.add_argument('-s', action='store_true', help='Show remaining seconds')
    parser.add_argument('-t', action='store_true', help='Show remaining time')
    
    
    
    args = parser.parse_args()
    
    # Default settings
    profile = "techops"
    credentials_file = str(Path.home() / ".aws" / "credentials")
    
    # Get expiration time from credentials file
    expires = parse_credentials_file(profile, credentials_file)
    
    # Calculate remaining time
    remaining_seconds, formatted_time = calculate_remaining_time(expires)
    
    # Handle output format
    if args.s:
        print(remaining_seconds)
    elif args.t:
        print(formatted_time)
    else:  # Default or -f
        print(f"Remaining: {formatted_time}")

if __name__ == "__main__":
    main()