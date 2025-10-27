BEGIN;
SET search_path TO onboarding, public;
-- ====== SEATING (100 rows) ======

INSERT INTO seating_space (employee_ID, seat_type)
SELECT
  NULL::BIGINT AS employee_ID,
  CASE WHEN random() < 0.7 THEN 'cubicle' ELSE 'cabin' END AS seat_type
FROM generate_series(1, 100);

-- ====== EQUIPMENTS (100 rows) ======

WITH rows AS (
  SELECT
    i,
    (ARRAY['laptop','headphone','mic','webcam','phone'])[(floor(random()*5)+1)::int] AS equipment_type
  FROM generate_series(1, 100) AS g(i)
)
INSERT INTO equipments (employee_ID, equipment_type, os, serial_number)
SELECT
  NULL::BIGINT AS employee_ID,
  r.equipment_type,
  CASE
    WHEN r.equipment_type = 'laptop'
      THEN (ARRAY['linux','windows','macos'])[(floor(random()*3)+1)::int]
    ELSE NULL
  END AS os,
  (
    CASE r.equipment_type
      WHEN 'laptop'   THEN 'LT'
      WHEN 'headphone' THEN 'HP'
      WHEN 'mic'      THEN 'MC'
      WHEN 'webcam'   THEN 'WC'
      WHEN 'phone'    THEN 'PH'
      ELSE 'EQ'
    END
  ) || '-' || to_char(r.i, 'FM000000') AS serial_number
FROM rows r;

COMMIT;