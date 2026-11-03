-- Analytical queries for the Retail Sales database.
-- Each query starts with a "-- name: <query_name>" marker so that
-- src/analytics.py can load and run them by name.
-- You can also paste any query into a SQLite client (e.g. the "SQLite Viewer"
-- VS Code extension or `sqlite3 database/retail_sales.db`).

-- name: total_revenue
SELECT ROUND(SUM(total_sales), 2) AS total_revenue
FROM sales;

-- name: total_orders
SELECT COUNT(DISTINCT order_id) AS total_orders
FROM sales;

-- name: unique_customers
SELECT COUNT(DISTINCT customer_id) AS unique_customers
FROM sales
WHERE customer_id <> 'UNKNOWN';

-- name: revenue_by_category
SELECT p.category,
       ROUND(SUM(s.total_sales), 2) AS revenue,
       COUNT(*)                     AS orders
FROM sales AS s
JOIN products AS p ON p.product_name = s.product
GROUP BY p.category
ORDER BY revenue DESC;

-- name: monthly_sales_trend
SELECT strftime('%Y-%m', order_date) AS month,
       ROUND(SUM(total_sales), 2)    AS revenue,
       COUNT(*)                      AS orders
FROM sales
GROUP BY month
ORDER BY month;

-- name: top_5_products
SELECT product,
       ROUND(SUM(total_sales), 2) AS revenue,
       SUM(quantity)              AS units_sold
FROM sales
GROUP BY product
ORDER BY revenue DESC
LIMIT 5;

-- name: regional_performance
SELECT region,
       ROUND(SUM(total_sales), 2)                                   AS revenue,
       COUNT(*)                                                     AS orders,
       ROUND(SUM(total_sales) * 100.0 / (SELECT SUM(total_sales) FROM sales), 1) AS revenue_share_pct
FROM sales
GROUP BY region
ORDER BY revenue DESC;
