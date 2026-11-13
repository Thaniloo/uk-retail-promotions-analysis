-- 01_profile.sql : data quality checks before any analysis
-- Row counts, date coverage, missing values and thin-history households.

-- name: row_counts
SELECT 'transactions' AS table_name, COUNT(*) AS n_rows FROM transactions
UNION ALL SELECT 'products', COUNT(*) FROM products
UNION ALL SELECT 'demographics', COUNT(*) FROM demographics
UNION ALL SELECT 'campaigns', COUNT(*) FROM campaigns
UNION ALL SELECT 'coupon_redemptions', COUNT(*) FROM coupon_redemptions;

-- name: coverage
SELECT MIN(DATE(transaction_timestamp)) AS first_day,
       MAX(DATE(transaction_timestamp)) AS last_day,
       COUNT(DISTINCT household_id)     AS households,
       COUNT(DISTINCT basket_id)        AS baskets,
       COUNT(DISTINCT store_id)         AS stores,
       COUNT(DISTINCT product_id)       AS products_sold,
       ROUND(SUM(sales_value), 0)       AS total_sales
FROM transactions;

-- name: missing_values
SELECT 'products.department'       AS column_name, SUM(department IS NULL)       AS n_missing, COUNT(*) AS n_rows FROM products
UNION ALL SELECT 'products.product_category', SUM(product_category IS NULL), COUNT(*) FROM products
UNION ALL SELECT 'products.product_type',     SUM(product_type IS NULL),     COUNT(*) FROM products
UNION ALL SELECT 'products.package_size',     SUM(package_size IS NULL),     COUNT(*) FROM products
UNION ALL SELECT 'demographics.income',       SUM(income IS NULL),           COUNT(*) FROM demographics
UNION ALL SELECT 'demographics.home_ownership', SUM(home_ownership IS NULL), COUNT(*) FROM demographics
UNION ALL SELECT 'transactions.zero_or_negative_sales', SUM(sales_value <= 0), COUNT(*) FROM transactions
UNION ALL SELECT 'transactions.product_not_in_catalogue',
          SUM(p.product_id IS NULL), COUNT(*)
          FROM transactions t LEFT JOIN products p USING (product_id);

-- name: basket_count_distribution
-- How many households have very few baskets? These are dropped from RFM and lift work.
WITH hh AS (
    SELECT household_id, COUNT(DISTINCT basket_id) AS baskets
    FROM transactions GROUP BY household_id
)
SELECT CASE WHEN baskets < 5   THEN '1-4'
            WHEN baskets < 10  THEN '5-9'
            WHEN baskets < 25  THEN '10-24'
            WHEN baskets < 50  THEN '25-49'
            WHEN baskets < 100 THEN '50-99'
            ELSE '100+' END AS baskets_in_year,
       COUNT(*) AS households
FROM hh
GROUP BY 1
ORDER BY MIN(baskets);
