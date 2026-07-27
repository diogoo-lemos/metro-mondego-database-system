-- -----------------------------------------------------------------------------
-- USERS (base table for all user types)
-- -----------------------------------------------------------------------------

CREATE TABLE users (
    user_id       SERIAL,
    username      VARCHAR(512) NOT NULL,
    email         VARCHAR(512) NOT NULL,
    password_hash VARCHAR(512) NOT NULL,
    created_at    TIMESTAMP    NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id),
    UNIQUE (username),
    UNIQUE (email)
);

-- -----------------------------------------------------------------------------
-- CUSTOMER (extends users)
-- -----------------------------------------------------------------------------

CREATE TABLE customer (
    name           VARCHAR(512) NOT NULL,
    nif            VARCHAR(9)   NOT NULL UNIQUE,
    phone          VARCHAR(20)  NOT NULL,
    wallet_balance FLOAT        NOT NULL DEFAULT 0.0,
    users_user_id  INTEGER      NOT NULL,
    PRIMARY KEY (users_user_id),
    UNIQUE  (nif),
    FOREIGN KEY (users_user_id) REFERENCES users(user_id)
);

-- -----------------------------------------------------------------------------
-- ADMINISTRATOR (extends users)
-- -----------------------------------------------------------------------------

CREATE TABLE administrator (
    name          VARCHAR(512) NOT NULL,
    is_super      BOOLEAN      NOT NULL DEFAULT FALSE,
    users_user_id INTEGER      NOT NULL,
    PRIMARY KEY (users_user_id),
    FOREIGN KEY (users_user_id) REFERENCES users(user_id)
);

-- -----------------------------------------------------------------------------
-- LINE + LINE OPERATION (merged entity)
-- -----------------------------------------------------------------------------

CREATE TABLE line_lineoperation (
    line_id                  SERIAL,
    name                     VARCHAR(512) NOT NULL,
    type                     VARCHAR(50)  NOT NULL,   -- 'urban' | 'regional'
    lineoperation_start_time TIME         NOT NULL,
    lineoperation_end_time   TIME         NOT NULL,
    lineoperation_frequency  INTEGER      NOT NULL,   -- minutes between departures
    lineoperation_capacity   INTEGER      NOT NULL DEFAULT 50,
    lineoperation_is_open    BOOLEAN      NOT NULL DEFAULT TRUE,
    PRIMARY KEY (line_id),
    CONSTRAINT chk_line_type      CHECK (type IN ('urban', 'regional')),
    CONSTRAINT chk_line_frequency CHECK (lineoperation_frequency > 0),
    CONSTRAINT chk_line_capacity  CHECK (lineoperation_capacity  > 0)
);

-- -----------------------------------------------------------------------------
-- STATION
-- -----------------------------------------------------------------------------

CREATE TABLE station (
    station_id SERIAL,
    name       VARCHAR(512) NOT NULL,
    PRIMARY KEY (station_id),
    UNIQUE (name)
);

-- -----------------------------------------------------------------------------
-- LINE-STATION (ordered list of stations per line)
-- -----------------------------------------------------------------------------

CREATE TABLE linestation (
    position                   INTEGER NOT NULL,
    station_station_id         INTEGER NOT NULL,
    line_lineoperation_line_id INTEGER NOT NULL,
    PRIMARY KEY (station_station_id, line_lineoperation_line_id),
    FOREIGN KEY (station_station_id)         REFERENCES station(station_id),
    FOREIGN KEY (line_lineoperation_line_id) REFERENCES line_lineoperation(line_id),
    CONSTRAINT chk_position CHECK (position >= 0)
);

-- -----------------------------------------------------------------------------
-- TRIP (a concrete scheduled departure of a line)
-- -----------------------------------------------------------------------------

CREATE TABLE trip (
    trip_id                    SERIAL,
    direction                  VARCHAR(20)  NOT NULL,  -- 'outbound' | 'inbound'
    departure_time             TIMESTAMP    NOT NULL,
    capacity                   INTEGER      NOT NULL,
    booked_seats               INTEGER      NOT NULL DEFAULT 0,
    line_lineoperation_line_id INTEGER      NOT NULL,
    PRIMARY KEY (trip_id, line_lineoperation_line_id),
    FOREIGN KEY (line_lineoperation_line_id) REFERENCES line_lineoperation(line_id),
    CONSTRAINT chk_direction    CHECK (direction IN ('outbound', 'inbound')),
    CONSTRAINT chk_capacity     CHECK (capacity     > 0),
    CONSTRAINT chk_booked_seats CHECK (booked_seats >= 0),
    CONSTRAINT chk_seats_limit  CHECK (booked_seats <= capacity)
);

-- -----------------------------------------------------------------------------
-- FARE TYPE (a type of ticket/pass per line)
-- -----------------------------------------------------------------------------

CREATE TABLE faretype (
    fare_type_id               SERIAL,
    type                       VARCHAR(50)  NOT NULL,
    line_lineoperation_line_id INTEGER      NOT NULL,
    PRIMARY KEY (fare_type_id),
    FOREIGN KEY (line_lineoperation_line_id) REFERENCES line_lineoperation(line_id),
    CONSTRAINT chk_fare_type CHECK (type IN (
        'single_trip', 'daily', 'monthly', 'monthly_student', 'monthly_senior'
    )),
    UNIQUE (line_lineoperation_line_id, type)  -- one fare type per line per product
);

-- -----------------------------------------------------------------------------
-- FARE HISTORY (price history per fare type)
-- -----------------------------------------------------------------------------

CREATE TABLE farehistory (
    fare_history_id       SERIAL,
    price                 FLOAT  NOT NULL,
    effective_from        DATE   NOT NULL,
    faretype_fare_type_id INTEGER NOT NULL,
    PRIMARY KEY (fare_history_id),
    FOREIGN KEY (faretype_fare_type_id) REFERENCES faretype(fare_type_id),
    CONSTRAINT chk_fare_price CHECK (price > 0)
);

-- -----------------------------------------------------------------------------
-- PROMOTION (discount rule per line + fare type + date range)
-- -----------------------------------------------------------------------------

CREATE TABLE promotion (
    promotion_id               SERIAL,
    name                       VARCHAR(512) NOT NULL,
    discount_percent           FLOAT        NOT NULL,
    start_date                 DATE         NOT NULL,
    end_date                   DATE         NOT NULL,
    line_lineoperation_line_id INTEGER      NOT NULL,
    faretype_fare_type_id      INTEGER      NOT NULL,
    PRIMARY KEY (promotion_id),
    FOREIGN KEY (line_lineoperation_line_id) REFERENCES line_lineoperation(line_id),
    FOREIGN KEY (faretype_fare_type_id)      REFERENCES faretype(fare_type_id),
    CONSTRAINT chk_discount      CHECK (discount_percent > 0 AND discount_percent <= 100),
    CONSTRAINT chk_promo_dates   CHECK (start_date < end_date)
);

-- -----------------------------------------------------------------------------
-- PURCHASE (a ticket/pass bought by a customer)
-- -----------------------------------------------------------------------------

CREATE TABLE purchase (
    purchase_id            SERIAL,
    travel_date            DATE      NOT NULL,
    final_price            FLOAT     NOT NULL,
    purchased_at           TIMESTAMP NOT NULL DEFAULT NOW(),
    promotion_promotion_id INTEGER,              -- nullable: no promotion = full price
    faretype_fare_type_id  INTEGER   NOT NULL,
    customer_users_user_id INTEGER   NOT NULL,
    PRIMARY KEY (purchase_id),
    FOREIGN KEY (promotion_promotion_id) REFERENCES promotion(promotion_id),
    FOREIGN KEY (faretype_fare_type_id)  REFERENCES faretype(fare_type_id),
    FOREIGN KEY (customer_users_user_id) REFERENCES customer(users_user_id),
    CONSTRAINT chk_purchase_price CHECK (final_price >= 0)
);

-- -----------------------------------------------------------------------------
-- TICKET VALIDATION (records each time a ticket is used)
-- -----------------------------------------------------------------------------

CREATE TABLE ticketvalidation (
    validation_id        SERIAL,
    used_at              TIMESTAMP NOT NULL,
    purchase_purchase_id INTEGER   NOT NULL,
    station_station_id   INTEGER   NOT NULL,
    PRIMARY KEY (validation_id),
    FOREIGN KEY (purchase_purchase_id) REFERENCES purchase(purchase_id),
    FOREIGN KEY (station_station_id)   REFERENCES station(station_id)
);

-- -----------------------------------------------------------------------------
-- WALLET TRANSACTION (records top-ups)
-- -----------------------------------------------------------------------------

CREATE TABLE wallettransaction (
    transaction_id         SERIAL,
    amount                 FLOAT        NOT NULL,
    payment_method         VARCHAR(50)  NOT NULL,
    created_at             TIMESTAMP    NOT NULL DEFAULT NOW(),
    customer_users_user_id INTEGER      NOT NULL,
    PRIMARY KEY (transaction_id),
    FOREIGN KEY (customer_users_user_id) REFERENCES customer(users_user_id),
    CONSTRAINT chk_topup_amount CHECK (amount > 0)
);

-- -----------------------------------------------------------------------------
-- NOTICE (broadcast messages sent by admins)
-- -----------------------------------------------------------------------------

CREATE TABLE notice (
    notice_id                   SERIAL,
    title                       VARCHAR(512) NOT NULL,
    message                     TEXT         NOT NULL,
    sent_at                     TIMESTAMP    NOT NULL DEFAULT NOW(),
    administrator_users_user_id INTEGER      NOT NULL,
    PRIMARY KEY (notice_id),
    FOREIGN KEY (administrator_users_user_id) REFERENCES administrator(users_user_id)
);

-- -----------------------------------------------------------------------------
-- CUSTOMER NOTICE (delivery + read status per customer)
-- -----------------------------------------------------------------------------

CREATE TABLE customernotice (
    read_at                TIMESTAMP,   -- NULL = not yet read
    customer_users_user_id INTEGER NOT NULL,
    notice_notice_id       INTEGER NOT NULL,
    PRIMARY KEY (customer_users_user_id, notice_notice_id),
    FOREIGN KEY (customer_users_user_id) REFERENCES customer(users_user_id),
    FOREIGN KEY (notice_notice_id)       REFERENCES notice(notice_id)
);

-- -----------------------------------------------------------------------------
-- TRIP PURCHASE (associates a single_trip purchase to a specific trip)
-- -----------------------------------------------------------------------------

CREATE TABLE trip_purchase (
    trip_trip_id                    INTEGER NOT NULL,
    trip_line_lineoperation_line_id INTEGER NOT NULL,
    purchase_purchase_id            INTEGER NOT NULL,
    PRIMARY KEY (trip_trip_id, trip_line_lineoperation_line_id, purchase_purchase_id),
    UNIQUE  (purchase_purchase_id),   -- one purchase maps to at most one trip
    FOREIGN KEY (trip_trip_id, trip_line_lineoperation_line_id)
        REFERENCES trip(trip_id, line_lineoperation_line_id),
    FOREIGN KEY (purchase_purchase_id)
        REFERENCES purchase(purchase_id)
);

-- -----------------------------------------------------------------------------
-- INDEXES (performance)
-- -----------------------------------------------------------------------------

-- Frequently queried in schedule lookups
CREATE INDEX idx_trip_departure        ON trip(departure_time);
CREATE INDEX idx_trip_line             ON trip(line_lineoperation_line_id);

-- Frequently queried in report aggregations
CREATE INDEX idx_ticketvalidation_used ON ticketvalidation(used_at);
CREATE INDEX idx_purchase_customer     ON purchase(customer_users_user_id);
CREATE INDEX idx_purchase_date         ON purchase(purchased_at);
CREATE INDEX idx_farehistory_effective ON farehistory(effective_from);
