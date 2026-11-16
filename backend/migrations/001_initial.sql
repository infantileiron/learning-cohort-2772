-- MySQL 8 actual DDL; generated after acceptance, seed counters removed.
CREATE TABLE `audits` (
  `id` int NOT NULL AUTO_INCREMENT,
  `actor` varchar(100) DEFAULT NULL,
  `action` varchar(200) DEFAULT NULL,
  `created` varchar(40) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `interval_state` (
  `id` int NOT NULL AUTO_INCREMENT,
  `version` int NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `interval_revisions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `learner` varchar(60) NOT NULL,
  `segments` json NOT NULL,
  `status` varchar(20) DEFAULT 'processing',
  `idempotency_key` varchar(200) NOT NULL,
  `fingerprint` varchar(64) NOT NULL,
  `note` text,
  `requested_by` varchar(100) DEFAULT NULL,
  `created_at` varchar(40) DEFAULT NULL,
  `completed_at` varchar(40) DEFAULT NULL,
  `applied_version` int DEFAULT NULL,
  `error` text,
  `result` json DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `idempotency_key` (`idempotency_key`),
  KEY `ix_interval_revisions_learner` (`learner`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `training_intervals` (
  `id` int NOT NULL AUTO_INCREMENT,
  `learner` varchar(60) NOT NULL,
  `start_date` varchar(10) NOT NULL,
  `end_date` varchar(10) DEFAULT NULL,
  `revision_id` int DEFAULT NULL,
  `created_at` varchar(40) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_interval_segment` (`learner`,`start_date`),
  KEY `ix_intervals_learner_start` (`learner`,`start_date`),
  KEY `ix_training_intervals_learner` (`learner`),
  KEY `revision_id` (`revision_id`),
  CONSTRAINT `training_intervals_ibfk_1` FOREIGN KEY (`revision_id`) REFERENCES `interval_revisions` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `cohorts` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) DEFAULT NULL,
  `start_week` varchar(10) DEFAULT NULL,
  `end_week` varchar(10) DEFAULT NULL,
  `as_of` varchar(10) DEFAULT NULL,
  `horizon` int DEFAULT NULL,
  `state` varchar(20) DEFAULT NULL,
  `result` json DEFAULT NULL,
  `error` text,
  `interval_version` int DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `events` (
  `id` int NOT NULL AUTO_INCREMENT,
  `code` varchar(60) NOT NULL,
  `learner` varchar(60) NOT NULL,
  `occurred_at` varchar(40) NOT NULL,
  `course` varchar(40) DEFAULT NULL,
  `note` text,
  PRIMARY KEY (`id`),
  UNIQUE KEY `code` (`code`),
  KEY `ix_events_learner` (`learner`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `email` varchar(100) NOT NULL,
  `password` varchar(200) DEFAULT NULL,
  `role` varchar(20) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `interventions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `cohort_id` int DEFAULT NULL,
  `cohort_week` varchar(10) DEFAULT NULL,
  `week_index` int DEFAULT NULL,
  `note` text,
  `members` json DEFAULT NULL,
  `status` varchar(20) DEFAULT NULL,
  `interval_version` int DEFAULT NULL,
  `recheck` json DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `cohort_id` (`cohort_id`),
  CONSTRAINT `interventions_ibfk_1` FOREIGN KEY (`cohort_id`) REFERENCES `cohorts` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
