#!/bin/bash

# Athena Trader Deployment Script
# This script automates the deployment of the Athena Trader platform

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_NAME="athena-trader"
COMPOSE_FILE="docker-compose.yml"
ENV_FILE=".env"

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    
    # Check if .env file exists
    if [ ! -f "$ENV_FILE" ]; then
        log_warning ".env file not found. Creating from template..."
        cp .env.example .env
        log_warning "Please edit .env file with your configuration before running again."
        exit 1
    fi
    
    log_success "Prerequisites check passed"
}

# Build and start services
deploy_services() {
    local environment=${1:-development}
    
    log_info "Starting deployment for $environment environment..."
    
    # Pull latest images
    log_info "Pulling latest images..."
    docker-compose pull
    
    # Build custom images
    log_info "Building custom images..."
    docker-compose build --no-cache
    
    # Start services based on environment
    if [ "$environment" = "production" ]; then
        log_info "Starting production services with Nginx..."
        docker-compose --profile production up -d
    else
        log_info "Starting development services..."
        docker-compose up -d
    fi
    
    log_success "Services deployed successfully"
}

# Wait for services to be healthy
wait_for_services() {
    log_info "Waiting for services to be healthy..."
    
    local services=("postgres" "redis" "data-service" "risk-service" "executor-service" "strategy-service" "frontend")
    local max_attempts=30
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        local all_healthy=true
        
        for service in "${services[@]}"; do
            if ! docker-compose ps | grep -q "$service.*Up.*healthy"; then
                all_healthy=false
                break
            fi
        done
        
        if [ "$all_healthy" = true ]; then
            log_success "All services are healthy!"
            break
        fi
        
        log_info "Attempt $attempt/$max_attempts: Waiting for services..."
        sleep 10
        ((attempt++))
    done
    
    if [ $attempt -gt $max_attempts ]; then
        log_error "Services did not become healthy within expected time"
        docker-compose ps
        exit 1
    fi
}

# Run database migrations
run_migrations() {
    log_info "Running database migrations..."
    
    # Wait for database to be ready
    local max_attempts=30
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if docker-compose exec -T postgres pg_isready -U ${POSTGRES_USER:-athena} -d ${POSTGRES_DB:-athena_trader} &> /dev/null; then
            break
        fi
        
        log_info "Waiting for database... Attempt $attempt/$max_attempts"
        sleep 2
        ((attempt++))
    done
    
    if [ $attempt -gt $max_attempts ]; then
        log_error "Database did not become ready within expected time"
        exit 1
    fi
    
    log_success "Database is ready"
}

# Show service status
show_status() {
    log_info "Service status:"
    docker-compose ps
    
    echo ""
    log_info "Service URLs:"
    echo "Frontend: http://localhost:3000"
    echo "Risk Service: http://localhost:8001"
    echo "Executor Service: http://localhost:8002"
    echo "Strategy Service: http://localhost:8003"
    echo "Data Service: http://localhost:8004"
    echo "PostgreSQL: localhost:5432"
    echo "Redis: localhost:6379"
}

# Cleanup function
cleanup() {
    log_info "Cleaning up..."
    docker-compose down -v
    docker system prune -f
    log_success "Cleanup completed"
}

# Backup function
backup_data() {
    local backup_dir="backups/$(date +%Y%m%d_%H%M%S)"
    
    log_info "Creating backup in $backup_dir..."
    mkdir -p "$backup_dir"
    
    # Backup database
    docker-compose exec -T postgres pg_dump -U ${POSTGRES_USER:-athena} ${POSTGRES_DB:-athena_trader} > "$backup_dir/database.sql"
    
    # Backup Redis data
    docker-compose exec -T redis redis-cli --rdb /tmp/dump.rdb
    docker cp $(docker-compose ps -q redis):/tmp/dump.rdb "$backup_dir/redis.rdb"
    
    # Backup configuration
    cp -r config "$backup_dir/"
    
    log_success "Backup completed: $backup_dir"
}

# Show logs
show_logs() {
    local service=${1:-}
    
    if [ -z "$service" ]; then
        log_info "Showing logs for all services..."
        docker-compose logs -f
    else
        log_info "Showing logs for $service..."
        docker-compose logs -f "$service"
    fi
}

# Main menu
show_menu() {
    echo ""
    echo "Athena Trader Deployment Script"
    echo "============================="
    echo "1. Deploy (Development)"
    echo "2. Deploy (Production)"
    echo "3. Stop Services"
    echo "4. Restart Services"
    echo "5. Show Status"
    echo "6. Show Logs"
    echo "7. Backup Data"
    echo "8. Cleanup"
    echo "9. Exit"
    echo ""
}

# Main execution
main() {
    check_prerequisites
    
    case "${1:-}" in
        "deploy-dev")
            deploy_services "development"
            wait_for_services
            show_status
            ;;
        "deploy-prod")
            deploy_services "production"
            wait_for_services
            show_status
            ;;
        "stop")
            log_info "Stopping services..."
            docker-compose down
            log_success "Services stopped"
            ;;
        "restart")
            log_info "Restarting services..."
            docker-compose restart
            wait_for_services
            show_status
            ;;
        "status")
            show_status
            ;;
        "logs")
            show_logs "${2:-}"
            ;;
        "backup")
            backup_data
            ;;
        "cleanup")
            cleanup
            ;;
        "menu")
            while true; do
                show_menu
                read -p "Please select an option: " choice
                case $choice in
                    1)
                        deploy_services "development"
                        wait_for_services
                        show_status
                        ;;
                    2)
                        deploy_services "production"
                        wait_for_services
                        show_status
                        ;;
                    3)
                        docker-compose down
                        log_success "Services stopped"
                        ;;
                    4)
                        docker-compose restart
                        wait_for_services
                        show_status
                        ;;
                    5)
                        show_status
                        ;;
                    6)
                        read -p "Enter service name (or press Enter for all): " service
                        show_logs "$service"
                        ;;
                    7)
                        backup_data
                        ;;
                    8)
                        cleanup
                        ;;
                    9)
                        log_info "Exiting..."
                        exit 0
                        ;;
                    *)
                        log_error "Invalid option"
                        ;;
                esac
                echo ""
            done
            ;;
        *)
            log_info "Usage: $0 {deploy-dev|deploy-prod|stop|restart|status|logs|backup|cleanup|menu}"
            echo ""
            echo "Common commands:"
            echo "  $0 deploy-dev     - Deploy development environment"
            echo "  $0 deploy-prod    - Deploy production environment"
            echo "  $0 stop          - Stop all services"
            echo "  $0 restart       - Restart all services"
            echo "  $0 status        - Show service status"
            echo "  $0 logs [service] - Show logs"
            echo "  $0 backup        - Backup data"
            echo "  $0 cleanup       - Cleanup containers and images"
            echo "  $0 menu          - Show interactive menu"
            ;;
    esac
}

# Execute main function with all arguments
main "$@"
