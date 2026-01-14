# app/services/incident_scheduler.py
import asyncio
from typing import Callable, Optional
from app.services.servicenow_fetcher import ServiceNowIncidentFetcher
from app.orchestrator import OrchestrationAgent

class IncidentScheduler:
    """Background scheduler to pull incidents from ServiceNow and process them"""
    
    def __init__(
        self,
        fetcher: ServiceNowIncidentFetcher,
        orchestrator: OrchestrationAgent,
        poll_interval: int = 30,  # Poll every 30 seconds
        incidents_per_poll: int = 5  # Process up to 5 incidents per poll
    ):
        self.fetcher = fetcher
        self.orchestrator = orchestrator
        self.poll_interval = poll_interval
        self.incidents_per_poll = incidents_per_poll
        self.running = False
        self.task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Start the incident polling scheduler"""
        if self.running:
            print("Incident scheduler already running")
            return
        
        self.running = True
        print(f"Starting incident scheduler (poll interval: {self.poll_interval}s, incidents per poll: {self.incidents_per_poll})")
        self.task = asyncio.create_task(self._poll_loop())
    
    async def stop(self):
        """Stop the incident polling scheduler"""
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        print("Incident scheduler stopped")
    
    async def _poll_loop(self):
        """Main polling loop"""
        while self.running:
            print(f"DEBUG: Starting periodic poll at {asyncio.get_event_loop().time()}")
            try:
                await self._process_incidents()
            except Exception as e:
                print(f"Error in incident scheduler: {e}")
            
            # Wait before next poll
            await asyncio.sleep(self.poll_interval)
    
    async def _process_incidents(self):
        """Fetch and process incidents from ServiceNow"""
        try:
            # Fetch open incidents with limit
            incident_requests = await self.fetcher.fetch_open_incidents(limit=self.incidents_per_poll)
            
            if not incident_requests:
                return
            
            print(f"Processing {len(incident_requests)} incidents from ServiceNow")
            
            # Process each incident through the orchestration pipeline sequentially
            for incident_req in incident_requests:
                try:
                    incident_num = incident_req.incident_number or "UNKNOWN"
                    print(f"\n>>> Processing incident: {incident_num}")
                    response = await self.orchestrator.run(incident_req.dict())
                    print(f"<<< Incident {incident_num} completed: {response}\n")
                except Exception as e:
                    incident_num = getattr(incident_req, 'incident_number', 'UNKNOWN') or 'UNKNOWN'
                    print(f"ERROR processing incident {incident_num}: {e}\n")
        
        except Exception as e:
            print(f"ERROR in incident scheduler loop: {e}")
