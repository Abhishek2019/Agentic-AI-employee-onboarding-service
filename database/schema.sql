CREATE SCHEMA onboarding;
SET search_path TO onboarding, public;

-- EMPLOYEES
CREATE TABLE employees (
  employee_ID BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name        VARCHAR(100) NOT NULL,
  email       VARCHAR(255) NOT NULL UNIQUE,
  phone       VARCHAR(32),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- SEATING_SPACE
CREATE TABLE seating_space (
  seat_ID     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  employee_ID BIGINT NULL,
  seat_type   VARCHAR(50) NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT fk_seat_emp
    FOREIGN KEY (employee_ID)
    REFERENCES employees(employee_ID)
    ON DELETE SET NULL
);
CREATE INDEX idx_seating_space_employee ON seating_space(employee_ID);

-- EQUIPMENTS
CREATE TABLE equipments (
  equipment_ID  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  employee_ID   BIGINT NULL,
  equipment_type VARCHAR(50) NOT NULL,
  os            VARCHAR(20),
  serial_number VARCHAR(64) NOT NULL UNIQUE,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT fk_equipment_emp
    FOREIGN KEY (employee_ID)
    REFERENCES employees(employee_ID)
    ON DELETE SET NULL
);
CREATE INDEX idx_equipments_employee ON equipments(employee_ID);
