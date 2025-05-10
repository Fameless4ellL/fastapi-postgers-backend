# Blocker Service

## Overview
The `blocker` service is a Python-based microservice designed to handle specific events related to blocking operations. It uses Redis as a backend for data storage and communication.

## Features
- Python 3.13.1-based service.
- Redis integration for data storage and communication.
- Lightweight and containerized using Docker.

## Requirements
- Python 3.13.1
- Redis
- Docker (for containerized deployment)

## NOTE

### Required Environment Variables
To run the `blocker` service, ensure the following environment variables are set in a `.env` file or your environment:
- `REDIS_HOST`: Hostname of the Redis server (default: `redis`).
- `REDIS_PORT`: Port of the Redis server (default: `6379`).

### Required Redis Data
The following keys and data must exist in Redis for the service to function properly:
- `BLOCKER:STATE:<net_label>`: Stores the state for a specific network label.
- `BLOCKER:NET`: A JSON-encoded list of networks.
- `BLOCKER:ERC20:<net_label>`: A set of ERC20 tokens for a specific network label.
- `BLOCKER:WALLETS`: A set of wallet addresses.
- `EVENT_KEY`: A string key for event handling.

Ensure these keys are populated in Redis before running the service.