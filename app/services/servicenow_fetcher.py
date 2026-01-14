# app/services/servicenow_fetcher.py
import asyncio
import json
from typing import List, Dict, Any
from app.clients.servicenow_client import ServiceNowClient
from app.models import IncidentRequest

class ServiceNowIncidentFetcher:
    """Fetches open incidents from ServiceNow and converts them to IncidentRequest format"""
    
    def __init__(self, snow_client: ServiceNowClient):
        self.snow_client = snow_client
        self.processed_incidents = set()  # Track processed incident IDs
    
    async def fetch_open_incidents(self, limit: int = 10) -> List[IncidentRequest]:
        """
        Fetch incidents from ServiceNow and strictly verify both state 'New' (state=1) and assignment group 'Infra-team'.
        Limit to prevent overwhelming the system (default 10 incidents per poll)
        """
        try:
            # Query for incidents that are likely to match, but always verify both state and assignment group in post-filter
            query = "state=1^assignment_group.name=Infra-team"
            incidents = await self.snow_client.query_incidents(query, limit=limit)

            # DEBUG: Print raw incidents for troubleshooting
            print("DEBUG: Raw incidents from ServiceNow:", incidents)

            # Post-filter incidents by state and assignment group

            # POST-FETCH FILTER: Only keep incidents with assignment_group display value 'Infra-team' AND state '1' (New)
            filtered_incidents = []
            for incident in incidents:
                if not isinstance(incident, dict):
                    continue
                agroup = incident.get('assignment_group')
                agroup_id = None
                agroup_name = "unknown"
                if isinstance(agroup, dict):
                    agroup_id = agroup.get('value')
                    agroup_name = agroup.get('display_value', 'unknown')
                elif isinstance(agroup, str):
                    agroup_id = agroup
                
                matched_group = (agroup_id == "04d7f8c4c38e3610cf197cec050131f5")
                print(f"DEBUG: Incident {incident.get('number')} group_id: {agroup_id}, group_name: {agroup_name}, matched: {matched_group}")
                
                # Check both 'state' and 'incident_state' fields
                state_val = str(incident.get('state', '')).strip()
                incident_state_val = str(incident.get('incident_state', '')).strip()
                
                # Match by assignment_group sys_id for Infra-team and state '1' (New)
                # Note: We temporarily allow ANY group if it matches the name filter in the query to see what we get
                if (state_val == '1' or incident_state_val == '1'):
                    filtered_incidents.append(incident)

            if not filtered_incidents:
                print("No incidents with state 'New' and assignment group 'Infra-team' found in ServiceNow (post-filter)")
                return []

            print(f"Found {len(filtered_incidents)} incidents with state 'New' and assignment group 'Infra-team' in ServiceNow (limit: {limit}, post-filter)")

            # Convert to IncidentRequest format
            incident_requests = []
            for incident in filtered_incidents:
                # Handle case where incident might be a string
                if isinstance(incident, str):
                    print(f"Skipping incident - invalid format (string): {incident[:100]}")
                    continue
                if not isinstance(incident, dict):
                    print(f"Skipping incident - invalid format (not dict): {type(incident)}")
                    continue
                sys_id = incident.get('sys_id')
                # Skip if already processed
                if sys_id in self.processed_incidents:
                    continue
                # Extract relevant fields
                number = incident.get('number')
                short_desc = incident.get('short_description', '')
                description = incident.get('description', '')
                # Handle cmdb_ci which might be a dict or string
                cmdb_ci = incident.get('cmdb_ci', {})
                if isinstance(cmdb_ci, dict):
                    system = cmdb_ci.get('value', 'unknown')
                else:
                    system = str(cmdb_ci) if cmdb_ci else 'unknown'
                severity = incident.get('severity', '3')  # 1=High, 2=Medium, 3=Low
                # Map ServiceNow severity to our format
                severity_map = {'1': 'critical', '2': 'high', '3': 'medium', '4': 'low'}
                mapped_severity = severity_map.get(str(severity), 'medium')
                # Create IncidentRequest
                incident_req = IncidentRequest(
                    incident_number=number,
                    description=f"{short_desc}\n{description}".strip(),
                    system=system or 'orchestrator',
                    severity=mapped_severity
                )
                incident_requests.append(incident_req)
                self.processed_incidents.add(sys_id)
                print(f"Queued incident {number} from ServiceNow: {short_desc}")

            return incident_requests

        except Exception as e:
            print(f"Error fetching ServiceNow incidents: {e}")
            return []
    
    async def get_incident_sys_id(self, incident_number: str) -> str:
        """Get the sys_id for a given incident number"""
        try:
            query = f"number={incident_number}"
            incidents = await self.snow_client.query_incidents(query)
            if incidents:
                return incidents[0].get('sys_id')
        except Exception as e:
            print(f"Error getting sys_id for {incident_number}: {e}")
        return None
    
    def mark_as_processed(self, sys_id: str):
        """Mark an incident as processed to avoid reprocessing"""
        self.processed_incidents.add(sys_id)
