-- 02_baseline.sql : headline numbers a category manager would expect to see first

-- name: weekly_sales
SELECT week,
       MIN(DATE(transaction_timestamp))   AS week_start,
       ROUND(SUM(sales_value), 2)         AS sales,
       COUNT(DISTINCT basket_id)          AS baskets,
       COUNT(DISTINCT household_id)       AS households,
       ROUND(SUM(retail_disc + coupon_disc + coupon_match_disc), 2) AS discount_given
FROM transactions
GROUP BY week
ORDER BY week;

-- name: basket_summary
WITH b AS (
    SELECT basket_id, SUM(sales_value) AS basket_value, COUNT(*) AS items   -- line items (quantity is unreliable for fuel)
    FROM transactions GROUP BY basket_id
)
SELECT COUNT(*)                 AS baskets,
       ROUND(AVG(basket_value), 2) AS avg_basket_value,
       ROUND(AVG(items), 1)        AS avg_lines_per_basket
FROM b;

-- name: top_categories
SELECT p.department,
       p.product_category,
       ROUND(SUM(t.sales_value), 0)                              AS revenue,
       COUNT(DISTINCT t.household_id)                            AS households_buying,
       ROUND(100.0 * SUM(t.retail_disc + t.coupon_disc) /
             NULLIF(SUM(t.sales_value + t.retail_disc + t.coupon_disc), 0), 1) AS pct_of_shelf_value_discounted
FROM transactions t
JOIN products p USING (product_id)
WHERE p.product_category IS NOT NULL AND p.department NOT IN ('MISCELLANEOUS','FUEL','COUPON','POSTAL CENTER','CHARITABLE CONT','PROD-WHS SALES','CNTRL/STORE SUP','GM MERCH EXP','KIOSK-GAS','MISC SALES TRAN')
GROUP BY p.department, p.product_category
ORDER BY revenue DESC
LIMIT 15;
