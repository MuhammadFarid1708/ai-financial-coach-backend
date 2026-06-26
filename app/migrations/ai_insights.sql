CREATE TABLE IF NOT EXISTS ai_insights (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL,
    insight_type VARCHAR(50) NOT NULL, -- e.g., 'budget', 'savings', 'debt'
    key_points TEXT[] NOT NULL,        -- Stores points as a clean array/list of strings
    full_summary TEXT NOT NULL,        -- Stores the full conversational text response
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);