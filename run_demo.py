import asyncio
import os
import sys

# Ensure src is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from atved.config import Settings
from atved.ingestion.kafka_producer import KafkaFrameProducer
from atved.ingestion.health_monitor import CameraHealthMonitor
from atved.ingestion.gateway import CameraGateway
import structlog

logger = structlog.get_logger()

async def run_demo(urls: list[str]):
    # Initialize basic settings
    settings = Settings()
    # Ensure we use the docker compose hostname for kafka
    settings.kafka.bootstrap_servers = "kafka:9092"
    
    logger.info("Initializing demo...")

    async with KafkaFrameProducer(settings) as producer:
        monitor = CameraHealthMonitor(settings)
        await monitor.start()
        
        gateway = CameraGateway(settings, producer, monitor)
        
        streams = {}
        for i, url in enumerate(urls):
            streams[f"mobile-cam-{i+1}"] = url
        
        logger.info("Starting Camera Gateway", streams=streams)
        await gateway.start(streams)
        
        try:
            # Let it run until user interrupts
            while True:
                await asyncio.sleep(5)
                logger.info("Demo running... Check Kafka topic 'camera-frames' for ingested frames.")
        except KeyboardInterrupt:
            logger.info("Stopping Gateway...")
        finally:
            await gateway.stop()
            await monitor.stop()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_demo.py <RTSP_URL_1> [RTSP_URL_2] ...")
        sys.exit(1)
        
    asyncio.run(run_demo(sys.argv[1:]))
