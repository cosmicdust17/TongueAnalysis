-- STEP 2: MySQL 8.0/8.4 initial schema, generated from the SQLAlchemy model.

-- Execute only on an empty business schema. This script does not DROP any table.

USE tongue_analysis;


CREATE TABLE alerts (
	id VARCHAR(36) NOT NULL, 
	service VARCHAR(80) NOT NULL, 
	message VARCHAR(240) NOT NULL, 
	resolved BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE audit_logs (
	id VARCHAR(36) NOT NULL, 
	actor_id VARCHAR(36), 
	actor_name VARCHAR(80) NOT NULL, 
	category VARCHAR(24) NOT NULL, 
	action VARCHAR(200) NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE INDEX ix_audit_logs_actor_id ON audit_logs (actor_id);

CREATE INDEX ix_audit_logs_created_at ON audit_logs (created_at);

CREATE TABLE users (
	id VARCHAR(36) NOT NULL, 
	username VARCHAR(80) NOT NULL, 
	openid VARCHAR(128), 
	password_hash VARCHAR(256) NOT NULL, 
	nickname VARCHAR(80) NOT NULL, 
	`role` VARCHAR(32) NOT NULL, 
	active BOOL NOT NULL, 
	token_version INTEGER NOT NULL, 
	profile JSON NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (username), 
	UNIQUE (openid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE stored_files (
	id VARCHAR(36) NOT NULL, 
	owner_id VARCHAR(36) NOT NULL, 
	original_name VARCHAR(255) NOT NULL, 
	path VARCHAR(512) NOT NULL, 
	content_type VARCHAR(120) NOT NULL, 
	purpose VARCHAR(24) NOT NULL, 
	size INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(owner_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE INDEX ix_stored_files_owner_id ON stored_files (owner_id);

CREATE TABLE analyses (
	id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	image_id VARCHAR(36) NOT NULL, 
	symptoms TEXT NOT NULL, 
	duration VARCHAR(40) NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	progress INTEGER NOT NULL, 
	error TEXT NOT NULL, 
	result JSON NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(image_id) REFERENCES stored_files (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE INDEX ix_analyses_status ON analyses (status);

CREATE INDEX ix_analyses_user_id ON analyses (user_id);

CREATE TABLE documents (
	id VARCHAR(36) NOT NULL, 
	file_id VARCHAR(36), 
	title VARCHAR(200) NOT NULL, 
	citation TEXT NOT NULL, 
	is_demo BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(file_id) REFERENCES stored_files (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE reports (
	id VARCHAR(36) NOT NULL, 
	analysis_id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	title VARCHAR(160) NOT NULL, 
	content JSON NOT NULL, 
	is_demo BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (analysis_id), 
	FOREIGN KEY(analysis_id) REFERENCES analyses (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE INDEX ix_reports_user_created ON reports (user_id, created_at);

CREATE INDEX ix_reports_user_id ON reports (user_id);

CREATE TABLE report_evidence (
	id VARCHAR(36) NOT NULL, 
	report_id VARCHAR(36) NOT NULL, 
	graph_entity_id VARCHAR(36) NOT NULL, 
	snapshot JSON NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(report_id) REFERENCES reports (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE INDEX ix_report_evidence_report_id ON report_evidence (report_id);


-- After this SQL route: cd backend; alembic stamp head
-- Alternatively, omit this file and run alembic upgrade head to create the tables.