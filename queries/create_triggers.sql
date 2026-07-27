-- -----------------------------------------------------------------------------
-- TRIGGER 1: Deduct wallet balance after a purchase is inserted
--
-- Fired AFTER INSERT on purchase.
-- Checks if the customer has sufficient balance.
-- If not, raises an exception and the INSERT is rolled back.
-- If yes, deducts the final_price from wallet_balance.
--
-- Second line of defence for the concurrency conflict
-- -----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION fn_deduct_wallet_on_purchase()
RETURNS TRIGGER AS $$
DECLARE
    current_balance FLOAT;
BEGIN
    -- Read current balance (row already locked by SELECT FOR UPDATE in Python)
    SELECT wallet_balance
    INTO current_balance
    FROM customer
    WHERE users_user_id = NEW.customer_users_user_id;

    -- Guard: reject purchase if balance is insufficient
    IF current_balance < NEW.final_price THEN
        RAISE EXCEPTION
            'Insufficient wallet balance. Current: %.2f, Required: %.2f',
            current_balance, NEW.final_price;
    END IF;

    -- Deduct the purchase price from the wallet
    UPDATE customer
    SET wallet_balance = wallet_balance - NEW.final_price
    WHERE users_user_id = NEW.customer_users_user_id;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_deduct_wallet_on_purchase
    AFTER INSERT ON purchase
    FOR EACH ROW
    EXECUTE FUNCTION fn_deduct_wallet_on_purchase();


-- -----------------------------------------------------------------------------
-- TRIGGER 2: Prevent booked_seats from exceeding capacity on trip
--
-- Fired BEFORE UPDATE on trip, specifically when booked_seats changes.
-- Acts as a second line of defence for concurrency conflict 
-- last seat race condition, in addition to the SELECT FOR UPDATE in Python.
-- -----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION fn_check_trip_capacity()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.booked_seats > NEW.capacity THEN
        RAISE EXCEPTION
            'Trip % is fully booked. Capacity: %, Booked: %',
            NEW.trip_id, NEW.capacity, NEW.booked_seats;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_check_trip_capacity
    BEFORE UPDATE OF booked_seats ON trip
    FOR EACH ROW
    EXECUTE FUNCTION fn_check_trip_capacity();


-- -----------------------------------------------------------------------------
-- TRIGGER 3: Prevent wallet_balance from going negative
--
-- Fired BEFORE UPDATE on customer, specifically when wallet_balance changes.
-- Third line of defence for the concurrency conflict,
-- ensuring the balance never goes below zero at the DB level
-- regardless of how the update is triggered.
-- -----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION fn_check_wallet_balance()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.wallet_balance < 0 THEN
        RAISE EXCEPTION
            'Wallet balance cannot be negative. Attempted balance: %.2f',
            NEW.wallet_balance;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_check_wallet_balance
    BEFORE UPDATE OF wallet_balance ON customer
    FOR EACH ROW
    EXECUTE FUNCTION fn_check_wallet_balance();


-- -----------------------------------------------------------------------------
-- TRIGGER 4: Prevent insertion of a purchase on a closed line
--
-- Fired BEFORE INSERT on purchase.
-- Checks whether the line associated with the faretype is currently open.
-- Rejects the purchase if the line is closed (is_open = FALSE).
-- -----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION fn_check_line_open_on_purchase()
RETURNS TRIGGER AS $$
DECLARE
    line_open BOOLEAN;
    v_line_id   INTEGER;
BEGIN
    -- Resolve the line from the faretype
    SELECT ft.line_lineoperation_line_id
    INTO v_line_id
    FROM faretype ft
    WHERE ft.fare_type_id = NEW.faretype_fare_type_id;

    -- Check if the line is open
    SELECT lineoperation_is_open
    INTO line_open
    FROM line_lineoperation
    WHERE line_id = v_line_id;

    IF NOT line_open THEN
        RAISE EXCEPTION
            'Cannot purchase ticket: line % is currently closed for operations.',
            v_line_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_check_line_open_on_purchase
    BEFORE INSERT ON purchase
    FOR EACH ROW
    EXECUTE FUNCTION fn_check_line_open_on_purchase();


-- -----------------------------------------------------------------------------
-- TRIGGER 5: Prevent duplicate single_trip validation
--
-- Fired BEFORE INSERT on ticketvalidation.
-- For single_trip tickets, ensures the ticket has not already been validated.
-- Acts as a second line of defence for concurrency conflict 
-- double validation race condition.
-- -----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION fn_check_single_trip_validation()
RETURNS TRIGGER AS $$
DECLARE
    product_type      VARCHAR(50);
    validation_count  INTEGER;
BEGIN
    -- Get the product type of the ticket being validated
    SELECT ft.type
    INTO product_type
    FROM purchase p
    JOIN faretype ft ON ft.fare_type_id = p.faretype_fare_type_id
    WHERE p.purchase_id = NEW.purchase_purchase_id;

    IF product_type = 'single_trip' THEN
        SELECT COUNT(*)
        INTO validation_count
        FROM ticketvalidation
        WHERE purchase_purchase_id = NEW.purchase_purchase_id;

        IF validation_count >= 1 THEN
            RAISE EXCEPTION
                'Single trip ticket % has already been used.',
                NEW.purchase_purchase_id;
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_check_single_trip_validation
    BEFORE INSERT ON ticketvalidation
    FOR EACH ROW
    EXECUTE FUNCTION fn_check_single_trip_validation();
