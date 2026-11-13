-- 05_promotions.sql : is promotional spend incremental, or a subsidy on habitual purchases?

-- name: coupon_already_buyer
-- For every coupon-discounted line, did the household already buy that product
-- at full price in the 8 weeks before? If so, the coupon mostly paid for a habit.
WITH coupon_lines AS (
    SELECT household_id, product_id, week, SUM(coupon_disc) AS coupon_disc, SUM(sales_value) AS sales
    FROM transactions WHERE coupon_disc > 0
    GROUP BY household_id, product_id, week
),
full_price AS (
    SELECT DISTINCT household_id, product_id, week
    FROM transactions WHERE coupon_disc = 0
)
SELECT cl.household_id, cl.product_id, cl.week, cl.coupon_disc, cl.sales,
       p.department, p.product_category,
       EXISTS (SELECT 1 FROM full_price fp
               WHERE fp.household_id = cl.household_id AND fp.product_id = cl.product_id
                 AND fp.week BETWEEN cl.week - 8 AND cl.week - 1) AS bought_before
FROM coupon_lines cl
JOIN products p USING (product_id)
WHERE cl.week > 8;

-- name: basket_halo
-- Within each household: baskets that contain a shelf-discounted item vs baskets that don't.
-- Compares the spend on NON-discounted items, i.e. does the promo pull the rest of the basket up?
WITH b AS (
    SELECT household_id, basket_id,
           MAX(retail_disc > 0)                                   AS has_promo_item,
           SUM(CASE WHEN retail_disc = 0 THEN sales_value END)    AS full_price_spend,
           SUM(CASE WHEN retail_disc > 0 THEN sales_value END)    AS promo_spend,
           SUM(retail_disc)                                       AS discount
    FROM transactions GROUP BY household_id, basket_id
)
SELECT household_id, has_promo_item,
       COUNT(*)                         AS baskets,
       AVG(COALESCE(full_price_spend,0)) AS avg_full_price_spend,
       AVG(COALESCE(promo_spend,0))      AS avg_promo_spend,
       AVG(discount)                     AS avg_discount
FROM b GROUP BY household_id, has_promo_item;

-- name: category_discount_dependence
-- Share of each category's units that were sold on a shelf discount.
SELECT p.product_category,
       ROUND(SUM(t.sales_value), 0) AS revenue,
       ROUND(100.0 * SUM(CASE WHEN t.retail_disc > 0 THEN t.quantity END) / SUM(t.quantity), 1) AS pct_units_on_discount,
       ROUND(SUM(t.retail_disc), 0) AS discount_cost
FROM transactions t JOIN products p USING (product_id)
WHERE p.product_category IS NOT NULL AND t.quantity > 0 AND p.department NOT IN ('MISCELLANEOUS','FUEL','COUPON','POSTAL CENTER','CHARITABLE CONT','PROD-WHS SALES','CNTRL/STORE SUP','GM MERCH EXP','KIOSK-GAS','MISC SALES TRAN')
GROUP BY p.product_category
HAVING SUM(t.sales_value) > 20000
ORDER BY discount_cost DESC;

-- name: basket_categories
-- Long table of (basket, category) used for association rules in Python.
SELECT DISTINCT t.basket_id, p.product_category
FROM transactions t JOIN products p USING (product_id)
WHERE p.product_category IS NOT NULL AND p.department NOT IN ('MISCELLANEOUS','FUEL','COUPON','POSTAL CENTER','CHARITABLE CONT','PROD-WHS SALES','CNTRL/STORE SUP','GM MERCH EXP','KIOSK-GAS','MISC SALES TRAN');
