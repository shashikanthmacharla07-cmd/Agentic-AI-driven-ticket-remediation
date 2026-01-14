#!/bin/bash
# AWX Playbook Setup Script
# This script creates sample playbooks in AWX for incident remediation

AWX_URL="http://172.16.0.5:30080"
AWX_TOKEN="iECGkeWAarxFlRqRIpQ9tspYrd0s6N"

echo "Testing AWX connectivity..."
curl -s -H "Authorization: Bearer $AWX_TOKEN" "$AWX_URL/api/v2/me/" || echo "Failed to connect to AWX"

echo ""
echo "Fetching existing job templates..."
curl -s -H "Authorization: Bearer $AWX_TOKEN" "$AWX_URL/api/v2/job_templates/" | python3 -m json.tool

echo ""
echo "To create playbooks, you need to:"
echo "1. SSH into AWX controller"
echo "2. Create playbooks in /var/lib/awx/projects/"
echo "3. Create Job Templates via AWX UI pointing to those playbooks"
echo ""
echo "Sample playbooks needed:"
echo "- restart-service.yml (for service failures)"
echo "- restart-app.yml (for app crashes)"
echo "- check-disk.yml (for disk space issues)"
echo "- check-database.yml (for DB connection issues)"
