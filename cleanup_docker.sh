#!/bin/bash
echo "Forcefully removing all containers associated with orchestrator..."
docker rm -f $(docker ps -a -q --filter "name=orchestrator") || true
docker rm -f 3afe10cd28d6 fc84f554bd11 5b4ad8d8e9a0 103007304b10 5ba2ba1808ba cc3487e8af89 f94a420cc22a || true
echo "Removing orphaned networks..."
docker network prune -f
echo "Cleanup complete."
