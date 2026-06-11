from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import threading
from sqlalchemy import inspect, text
from app.core.config import settings
from app.core.database import engine, Base
from app.routers import assistant, auth, workspaces, papers, chat, tools, system
from app.services.llm_service import llm_service

# Auto-create tables on startup (using declarative metadata)
Base.metadata.create_all(bind=engine)


def ensure_chat_session_schema() -> None:
    inspector = inspect(engine)
    if "chat_sessions" not in inspector.get_table_names():
        return

    # 1. Migrate chat_sessions if needed
    session_columns = {
        column["name"] for column in inspector.get_columns("chat_sessions")
    }
    
    # Check if a unique constraint index on workspace_id exists
    has_unique_workspace_id = False
    for index in inspector.get_indexes("chat_sessions"):
        if "workspace_id" in index["column_names"] and index["unique"]:
            # If the index is not just ix_chat_sessions_workspace_id or if it is unique
            has_unique_workspace_id = True
            break
            
    has_title = "title" in session_columns
    has_is_pinned = "is_pinned" in session_columns
    
    if not has_title or not has_is_pinned or has_unique_workspace_id:
        print("Migrating chat_sessions to support multiple sessions and new columns...")
        with engine.begin() as connection:
            connection.execute(text("PRAGMA foreign_keys = OFF"))
            
            # Create new table without unique constraint
            connection.execute(text(
                "CREATE TABLE chat_sessions_temp ("
                "id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, "
                "workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE, "
                "user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
                "title VARCHAR, "
                "is_pinned BOOLEAN NOT NULL DEFAULT 0, "
                "created_at DATETIME NOT NULL, "
                "updated_at DATETIME NOT NULL"
                ")"
            ))
            
            # Copy data
            select_cols = ["id", "workspace_id", "user_id"]
            if has_title:
                select_cols.append("title")
            else:
                select_cols.append("'New Chat' AS title")
                
            if has_is_pinned:
                select_cols.append("is_pinned")
            else:
                select_cols.append("0 AS is_pinned")
                
            select_cols.extend(["created_at", "updated_at"])
            
            cols_str = ", ".join(select_cols)
            connection.execute(text(
                f"INSERT INTO chat_sessions_temp (id, workspace_id, user_id, title, is_pinned, created_at, updated_at) "
                f"SELECT id, workspace_id, user_id, title, is_pinned, created_at, updated_at FROM ("
                f"SELECT {cols_str} FROM chat_sessions"
                f")"
            ))
            
            # Drop old unique index if any and drop table
            connection.execute(text("DROP TABLE chat_sessions"))
            connection.execute(text("ALTER TABLE chat_sessions_temp RENAME TO chat_sessions"))
            
            # Recreate indexes
            connection.execute(text("CREATE INDEX ix_chat_sessions_id ON chat_sessions (id)"))
            connection.execute(text("CREATE INDEX ix_chat_sessions_workspace_id ON chat_sessions (workspace_id)"))
            connection.execute(text("CREATE INDEX ix_chat_sessions_user_id ON chat_sessions (user_id)"))
            
            connection.execute(text("PRAGMA foreign_keys = ON"))
        print("chat_sessions migration complete.")

    # 2. Ensure chat_messages columns exist
    if "chat_messages" not in inspector.get_table_names():
        return

    message_columns = {
        column["name"] for column in inspector.get_columns("chat_messages")
    }
    is_legacy_schema = "workspace_id" in message_columns

    with engine.begin() as connection:
        if "session_id" not in message_columns:
            connection.execute(text(
                "ALTER TABLE chat_messages ADD COLUMN session_id INTEGER"
            ))
        if "timestamp" not in message_columns:
            connection.execute(text(
                "ALTER TABLE chat_messages ADD COLUMN timestamp DATETIME"
            ))

        if is_legacy_schema:
            connection.execute(text(
                "UPDATE chat_messages "
                "SET session_id = ("
                "SELECT chat_sessions.id FROM chat_sessions "
                "WHERE chat_sessions.workspace_id = chat_messages.workspace_id"
                ") WHERE session_id IS NULL"
            ))
        if "created_at" in message_columns:
            connection.execute(text(
                "UPDATE chat_messages SET timestamp = created_at "
                "WHERE timestamp IS NULL"
            ))
        connection.execute(text(
            "UPDATE chat_messages SET timestamp = CURRENT_TIMESTAMP "
            "WHERE timestamp IS NULL"
        ))

        if is_legacy_schema and engine.dialect.name == "sqlite":
            connection.execute(text(
                "CREATE TABLE chat_messages_migrated ("
                "id INTEGER NOT NULL PRIMARY KEY, "
                "session_id INTEGER NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE, "
                "role VARCHAR NOT NULL, "
                "content TEXT NOT NULL, "
                "timestamp DATETIME NOT NULL"
                ")"
            ))
            connection.execute(text(
                "INSERT INTO chat_messages_migrated "
                "(id, session_id, role, content, timestamp) "
                "SELECT id, session_id, role, content, timestamp FROM chat_messages"
            ))
            connection.execute(text("DROP TABLE chat_messages"))
            connection.execute(text(
                "ALTER TABLE chat_messages_migrated RENAME TO chat_messages"
            ))
            connection.execute(text(
                "CREATE INDEX ix_chat_messages_id ON chat_messages (id)"
            ))
            connection.execute(text(
                "CREATE INDEX ix_chat_messages_session_id "
                "ON chat_messages (session_id)"
            ))
        elif is_legacy_schema:
            connection.execute(text(
                "ALTER TABLE chat_messages ALTER COLUMN session_id SET NOT NULL"
            ))
            connection.execute(text(
                "ALTER TABLE chat_messages ALTER COLUMN timestamp SET NOT NULL"
            ))
            connection.execute(text(
                "ALTER TABLE chat_messages DROP COLUMN workspace_id"
            ))
            if "created_at" in message_columns:
                connection.execute(text(
                    "ALTER TABLE chat_messages DROP COLUMN created_at"
                ))


def ensure_paper_access_columns() -> None:
    inspector = inspect(engine)
    if "papers" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("papers")}
    access_columns = {
        "source": "VARCHAR",
        "doi": "VARCHAR",
        "doi_url": "VARCHAR",
        "source_url": "VARCHAR",
        "publisher_url": "VARCHAR",
        "ieee_url": "VARCHAR",
        "preferred_access_url": "VARCHAR",
        "preferred_access_type": "VARCHAR",
    }
    missing_columns = {
        name: column_type
        for name, column_type in access_columns.items()
        if name not in existing_columns
    }
    if not missing_columns:
        return

    with engine.begin() as connection:
        for name, column_type in missing_columns.items():
            connection.execute(text(f"ALTER TABLE papers ADD COLUMN {name} {column_type}"))

ensure_chat_session_schema()
ensure_paper_access_columns()

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# Set CORS origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth.router, prefix=settings.API_V1_STR)
app.include_router(workspaces.router, prefix=settings.API_V1_STR)
app.include_router(papers.router, prefix=settings.API_V1_STR)
app.include_router(chat.router, prefix=settings.API_V1_STR)
app.include_router(tools.router, prefix=settings.API_V1_STR)
app.include_router(assistant.router, prefix=settings.API_V1_STR)
app.include_router(system.router, prefix=settings.API_V1_STR)


@app.on_event("startup")
def provider_startup_self_test():
    llm_service.log_provider_configuration()

    def run_self_test() -> None:
        try:
            llm_service.provider_self_test()
        except Exception as exc:
            print(f"Provider startup self-test failed without crashing startup: {exc}")

    threading.Thread(target=run_self_test, daemon=True).start()

@app.get("/")
def read_root():
    return {
        "status": "online",
        "message": "Welcome to ResearchPilot AI Agent API Hub",
        "version": "1.0.0"
    }
