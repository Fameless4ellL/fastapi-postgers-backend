#!/usr/bin/sh

help_message() {
    echo "Usage: $0 <command>"
    echo "Commands:"
    echo "  migrate      Apply the latest migration"
    echo "  revert     Downgrade the last migration"
}

migrate() {
    local db=""

    echo "Select a database:"
    echo "1) default"
    echo "2) logs"
    echo -n "> "
    read -r choice

    case $choice in
        1) db="default" ;;
        2) db="logs" ;;
        *) echo "Invalid choice. Exiting."; return 1 ;;
    esac

    alembic -n "$db" upgrade head
}

revert() {
    local db=""

    echo "Select a database:"
    echo "1) default"
    echo "2) logs"
    echo -n "> "
    read -r choice

    case $choice in
        1) db="default" ;;
        2) db="logs" ;;
        *) echo "Invalid choice. Exiting."; return 1 ;;
    esac

    alembic -n "$db" downgrade -1
}

if [ "$#" -ne 1 ]; then
    echo "Error: Invalid number of arguments"
    help_message
    exit 1
fi

# Check the command and call the appropriate function
case "$1" in
    migrate)
        migrate
        ;;
    revert)
        migrate
        ;;
    *)
        echo "Invalid command: $1"
        help_message
        ;;
esac