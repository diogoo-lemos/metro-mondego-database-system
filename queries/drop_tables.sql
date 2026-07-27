-- =============================================================================
-- Drops all tables in the correct order (respecting foreign key dependencies)
-- Also drops triggers and functions to allow clean recreation
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Drop triggers first (they depend on functions)
-- -----------------------------------------------------------------------------

DROP TRIGGER IF EXISTS trg_deduct_wallet_on_purchase      ON purchase;
DROP TRIGGER IF EXISTS trg_check_trip_capacity            ON trip;
DROP TRIGGER IF EXISTS trg_check_wallet_balance           ON customer;
DROP TRIGGER IF EXISTS trg_check_line_open_on_purchase    ON purchase;
DROP TRIGGER IF EXISTS trg_check_single_trip_validation   ON ticketvalidation;

-- -----------------------------------------------------------------------------
-- Drop trigger functions
-- -----------------------------------------------------------------------------

DROP FUNCTION IF EXISTS fn_deduct_wallet_on_purchase();
DROP FUNCTION IF EXISTS fn_check_trip_capacity();
DROP FUNCTION IF EXISTS fn_check_wallet_balance();
DROP FUNCTION IF EXISTS fn_check_line_open_on_purchase();
DROP FUNCTION IF EXISTS fn_check_single_trip_validation();

-- -----------------------------------------------------------------------------
-- Drop tables (leaf tables first, then parent tables)
-- -----------------------------------------------------------------------------

DROP TABLE IF EXISTS trip_purchase      CASCADE;
DROP TABLE IF EXISTS ticketvalidation   CASCADE;
DROP TABLE IF EXISTS customernotice     CASCADE;
DROP TABLE IF EXISTS wallettransaction  CASCADE;
DROP TABLE IF EXISTS purchase           CASCADE;
DROP TABLE IF EXISTS promotion          CASCADE;
DROP TABLE IF EXISTS farehistory        CASCADE;
DROP TABLE IF EXISTS faretype           CASCADE;
DROP TABLE IF EXISTS trip               CASCADE;
DROP TABLE IF EXISTS linestation        CASCADE;
DROP TABLE IF EXISTS station            CASCADE;
DROP TABLE IF EXISTS notice             CASCADE;
DROP TABLE IF EXISTS customer           CASCADE;
DROP TABLE IF EXISTS administrator      CASCADE;
DROP TABLE IF EXISTS line_lineoperation CASCADE;
DROP TABLE IF EXISTS users              CASCADE;
