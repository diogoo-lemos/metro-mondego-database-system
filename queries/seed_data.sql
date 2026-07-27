-- This script populates the database with:
--   1. Super Administrator account
--   2. Fixed metro lines + operational parameters
--   3. Stations
--   4. Line-station associations (ordered)
--   5. Fare types per line
--   6. Initial fare prices
--   7. Trips for today and the next 7 days (generated from line schedules)

-- -----------------------------------------------------------------------------
-- 1. Super Administrator
--    username: superadmin | password: superadmin2026
--    Password hash generated with hashing.py 
-- -----------------------------------------------------------------------------

INSERT INTO users (username, email, password_hash, created_at)
VALUES (
    'superadmin',
    'superadmin@metromondego.pt',
    '3f98bee4a3dede1a829a21dba01c8b7f6a33746d30272d2f7a07fe7ff1cd7a75e1a41bfa46712c4fd9d83807878ad848cd4b52538b85d6d507fd08bdff701281',
    NOW()
);

INSERT INTO administrator (name, is_super, users_user_id)
VALUES (
    'Super Administrator',
    TRUE,
    (SELECT user_id FROM users WHERE username = 'superadmin')
);

-- -----------------------------------------------------------------------------
-- 2. Fixed Metro Lines
--    Line 1: Portagem – Hospital          (urban)
--    Line 2: Portagem – Estação B         (urban)
--    Line 3: Portagem – Serpins           (regional)
--
--    Schedules as defined in the project specification:
--    Line 1: 07:30 – 21:00, every 20 min (both directions)
--    Line 2: 07:45 – 19:00, every 30 min (both directions)
--    Line 3: asymmetric schedule (see trips section)
-- -----------------------------------------------------------------------------

INSERT INTO line_lineoperation
    (name, type, lineoperation_start_time, lineoperation_end_time,
     lineoperation_frequency, lineoperation_capacity, lineoperation_is_open)
VALUES
    ('Portagem-Hospital',  'urban',    '07:30', '21:00', 20, 50, TRUE),  -- line_id = 1
    ('Portagem-EstacaoB',  'urban',    '07:45', '19:00', 30, 50, TRUE),  -- line_id = 2
    ('Portagem-Serpins',   'regional', '07:00', '20:00', 30, 50, TRUE);  -- line_id = 3
-- Note: Line 3 frequency varies by direction and time window.
-- The lineoperation_frequency here stores the base value (30 min).
-- Actual trips are generated explicitly below to reflect the asymmetric schedule.

-- -----------------------------------------------------------------------------
-- 3. Stations
-- -----------------------------------------------------------------------------

INSERT INTO station (name) VALUES
    -- Shared
    ('Portagem'),               -- station_id = 1

    -- Line 1 stations
    ('Praça da República'),     -- station_id = 2
    ('Coimbra-B'),              -- station_id = 3
    ('Hospital'),               -- station_id = 4

    -- Line 2 stations
    ('Beira-Rio'),              -- station_id = 5
    ('Estação B'),              -- station_id = 6

    -- Line 3 stations
    ('Taveiro'),                -- station_id = 7
    ('Almalaguês'),             -- station_id = 8
    ('Miranda do Corvo'),       -- station_id = 9
    ('Serpins');                -- station_id = 10

-- -----------------------------------------------------------------------------
-- 4. Line-Station Associations (ordered by position)
-- -----------------------------------------------------------------------------

-- Line 1: Portagem → Praça da República → Coimbra-B → Hospital
INSERT INTO linestation (position, station_station_id, line_lineoperation_line_id) VALUES
    (0, 1, 1),   -- Portagem
    (1, 2, 1),   -- Praça da República
    (2, 3, 1),   -- Coimbra-B
    (3, 4, 1);   -- Hospital

-- Line 2: Portagem → Beira-Rio → Estação B
INSERT INTO linestation (position, station_station_id, line_lineoperation_line_id) VALUES
    (0, 1, 2),   -- Portagem
    (1, 5, 2),   -- Beira-Rio
    (2, 6, 2);   -- Estação B

-- Line 3: Portagem → Taveiro → Almalaguês → Miranda do Corvo → Serpins
INSERT INTO linestation (position, station_station_id, line_lineoperation_line_id) VALUES
    (0, 1,  3),  -- Portagem
    (1, 7,  3),  -- Taveiro
    (2, 8,  3),  -- Almalaguês
    (3, 9,  3),  -- Miranda do Corvo
    (4, 10, 3);  -- Serpins

-- -----------------------------------------------------------------------------
-- 5. Fare Types (one per product type per line)
-- -----------------------------------------------------------------------------

-- Line 1
INSERT INTO faretype (type, line_lineoperation_line_id) VALUES
    ('single_trip',     1),
    ('daily',           1),
    ('monthly',         1),
    ('monthly_student', 1),
    ('monthly_senior',  1);

-- Line 2
INSERT INTO faretype (type, line_lineoperation_line_id) VALUES
    ('single_trip',     2),
    ('daily',           2),
    ('monthly',         2),
    ('monthly_student', 2),
    ('monthly_senior',  2);

-- Line 3
INSERT INTO faretype (type, line_lineoperation_line_id) VALUES
    ('single_trip',     3),
    ('daily',           3),
    ('monthly',         3),
    ('monthly_student', 3),
    ('monthly_senior',  3);

-- -----------------------------------------------------------------------------
-- 6. Initial Fare Prices (effective from 2026-01-01)
-- -----------------------------------------------------------------------------

-- Line 1 prices
INSERT INTO farehistory (price, effective_from, faretype_fare_type_id) VALUES
    (1.60, '2026-01-01', (SELECT fare_type_id FROM faretype WHERE line_lineoperation_line_id = 1 AND type = 'single_trip')),
    (3.20, '2026-01-01', (SELECT fare_type_id FROM faretype WHERE line_lineoperation_line_id = 1 AND type = 'daily')),
    (40.00,'2026-01-01', (SELECT fare_type_id FROM faretype WHERE line_lineoperation_line_id = 1 AND type = 'monthly')),
    (20.00,'2026-01-01', (SELECT fare_type_id FROM faretype WHERE line_lineoperation_line_id = 1 AND type = 'monthly_student')),
    (18.00,'2026-01-01', (SELECT fare_type_id FROM faretype WHERE line_lineoperation_line_id = 1 AND type = 'monthly_senior'));

-- Line 2 prices
INSERT INTO farehistory (price, effective_from, faretype_fare_type_id) VALUES
    (1.60, '2026-01-01', (SELECT fare_type_id FROM faretype WHERE line_lineoperation_line_id = 2 AND type = 'single_trip')),
    (3.20, '2026-01-01', (SELECT fare_type_id FROM faretype WHERE line_lineoperation_line_id = 2 AND type = 'daily')),
    (40.00,'2026-01-01', (SELECT fare_type_id FROM faretype WHERE line_lineoperation_line_id = 2 AND type = 'monthly')),
    (20.00,'2026-01-01', (SELECT fare_type_id FROM faretype WHERE line_lineoperation_line_id = 2 AND type = 'monthly_student')),
    (18.00,'2026-01-01', (SELECT fare_type_id FROM faretype WHERE line_lineoperation_line_id = 2 AND type = 'monthly_senior'));

-- Line 3 prices (slightly higher — regional service)
INSERT INTO farehistory (price, effective_from, faretype_fare_type_id) VALUES
    (2.50, '2026-01-01', (SELECT fare_type_id FROM faretype WHERE line_lineoperation_line_id = 3 AND type = 'single_trip')),
    (5.00, '2026-01-01', (SELECT fare_type_id FROM faretype WHERE line_lineoperation_line_id = 3 AND type = 'daily')),
    (60.00,'2026-01-01', (SELECT fare_type_id FROM faretype WHERE line_lineoperation_line_id = 3 AND type = 'monthly')),
    (30.00,'2026-01-01', (SELECT fare_type_id FROM faretype WHERE line_lineoperation_line_id = 3 AND type = 'monthly_senior')),
    (25.00,'2026-01-01', (SELECT fare_type_id FROM faretype WHERE line_lineoperation_line_id = 3 AND type = 'monthly_student'));

-- -----------------------------------------------------------------------------
-- 7. Trips — generated for today + next 7 days
--
-- Line 1 (both directions): 07:30 → 21:00, every 20 min
-- Line 2 (both directions): 07:45 → 19:00, every 30 min
-- Line 3 outbound (Portagem → Serpins):
--     08:00 → 17:00 every 90 min, then 17:00 → 20:00 every 30 min
-- Line 3 inbound  (Serpins → Portagem):
--     07:00 → 09:30 every 30 min, then 09:30 → 19:00 every 90 min
--
-- Uses a DO block with a LOOP to avoid repeating INSERT statements.
-- -----------------------------------------------------------------------------

DO $$
DECLARE
    day_offset    INTEGER;
    base_date     DATE;
    dep_time      TIMESTAMP;
    minutes_step  INTEGER;
    start_minutes INTEGER;
    end_minutes   INTEGER;
    current_min   INTEGER;
    capacity_val  INTEGER := 50;
BEGIN
    FOR day_offset IN 0..7 LOOP
        base_date := CURRENT_DATE + day_offset;

        -- ---------------------------------------------------------------
        -- Line 1 outbound: 07:30 → 21:00, every 20 min
        -- ---------------------------------------------------------------
        current_min := 7 * 60 + 30;   -- 07:30
        end_minutes := 21 * 60;        -- 21:00
        WHILE current_min <= end_minutes LOOP
            INSERT INTO trip (direction, departure_time, capacity, booked_seats, line_lineoperation_line_id)
            VALUES (
                'outbound',
                (base_date + (current_min * INTERVAL '1 minute')),
                capacity_val, 0, 1
            );
            current_min := current_min + 20;
        END LOOP;

        -- ---------------------------------------------------------------
        -- Line 1 inbound: 07:30 → 21:00, every 20 min
        -- ---------------------------------------------------------------
        current_min := 7 * 60 + 30;
        WHILE current_min <= end_minutes LOOP
            INSERT INTO trip (direction, departure_time, capacity, booked_seats, line_lineoperation_line_id)
            VALUES (
                'inbound',
                (base_date + (current_min * INTERVAL '1 minute')),
                capacity_val, 0, 1
            );
            current_min := current_min + 20;
        END LOOP;

        -- ---------------------------------------------------------------
        -- Line 2 outbound: 07:45 → 19:00, every 30 min
        -- ---------------------------------------------------------------
        current_min := 7 * 60 + 45;   -- 07:45
        end_minutes := 19 * 60;        -- 19:00
        WHILE current_min <= end_minutes LOOP
            INSERT INTO trip (direction, departure_time, capacity, booked_seats, line_lineoperation_line_id)
            VALUES (
                'outbound',
                (base_date + (current_min * INTERVAL '1 minute')),
                capacity_val, 0, 2
            );
            current_min := current_min + 30;
        END LOOP;

        -- ---------------------------------------------------------------
        -- Line 2 inbound: 07:45 → 19:00, every 30 min
        -- ---------------------------------------------------------------
        current_min := 7 * 60 + 45;
        WHILE current_min <= end_minutes LOOP
            INSERT INTO trip (direction, departure_time, capacity, booked_seats, line_lineoperation_line_id)
            VALUES (
                'inbound',
                (base_date + (current_min * INTERVAL '1 minute')),
                capacity_val, 0, 2
            );
            current_min := current_min + 30;
        END LOOP;

        -- ---------------------------------------------------------------
        -- Line 3 inbound (Serpins → Portagem):
        --   07:00 → 09:30 every 30 min
        --   09:30 → 19:00 every 90 min
        -- ---------------------------------------------------------------
        current_min := 7 * 60;         -- 07:00
        end_minutes := 9 * 60 + 30;    -- 09:30
        WHILE current_min <= end_minutes LOOP
            INSERT INTO trip (direction, departure_time, capacity, booked_seats, line_lineoperation_line_id)
            VALUES (
                'inbound',
                (base_date + (current_min * INTERVAL '1 minute')),
                capacity_val, 0, 3
            );
            current_min := current_min + 30;
        END LOOP;

        -- 09:30 → 19:00 every 90 min (skip 09:30 already inserted)
        current_min := 9 * 60 + 30 + 90;  -- 11:00
        end_minutes := 19 * 60;
        WHILE current_min <= end_minutes LOOP
            INSERT INTO trip (direction, departure_time, capacity, booked_seats, line_lineoperation_line_id)
            VALUES (
                'inbound',
                (base_date + (current_min * INTERVAL '1 minute')),
                capacity_val, 0, 3
            );
            current_min := current_min + 90;
        END LOOP;

        -- ---------------------------------------------------------------
        -- Line 3 outbound (Portagem → Serpins):
        --   08:00 → 17:00 every 90 min
        --   17:00 → 20:00 every 30 min
        -- ---------------------------------------------------------------
        current_min := 8 * 60;         -- 08:00
        end_minutes := 17 * 60;        -- 17:00
        WHILE current_min <= end_minutes LOOP
            INSERT INTO trip (direction, departure_time, capacity, booked_seats, line_lineoperation_line_id)
            VALUES (
                'outbound',
                (base_date + (current_min * INTERVAL '1 minute')),
                capacity_val, 0, 3
            );
            current_min := current_min + 90;
        END LOOP;

        -- 17:00 → 20:00 every 30 min (skip 17:00 already inserted)
        current_min := 17 * 60 + 30;   -- 17:30
        end_minutes := 20 * 60;        -- 20:00
        WHILE current_min <= end_minutes LOOP
            INSERT INTO trip (direction, departure_time, capacity, booked_seats, line_lineoperation_line_id)
            VALUES (
                'outbound',
                (base_date + (current_min * INTERVAL '1 minute')),
                capacity_val, 0, 3
            );
            current_min := current_min + 30;
        END LOOP;

    END LOOP; -- day_offset
END $$;
