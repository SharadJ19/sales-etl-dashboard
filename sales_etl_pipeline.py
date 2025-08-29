# ----------------- sales_etl_pipeline.py -----------------
import pandas as pd
from random import randint, choice
import datetime
from sqlalchemy import create_engine, text
import matplotlib.pyplot as plt
import seaborn as sns
from faker import Faker
import os

# ----------------- INITIAL SETUP -----------------
fake = Faker()
os.makedirs('static/plots', exist_ok=True)  # folder for plots

# ----------------- ETL FUNCTION -----------------
def run_etl(db_config):
    print("Running ETL...")

    # ---------- GENERATE CSV DATA ----------
    num_customers = 200
    num_products = 50
    num_orders = 3000
    categories = ['Electronics','Clothing','Books','Toys','Home','Sports']
    start_date = datetime.date(2025,1,1)

    # Customers
    customers = pd.DataFrame({
        'customer_id': range(1, num_customers+1),
        'name': [fake.name() for _ in range(num_customers)],
        'email': [fake.unique.email() for _ in range(num_customers)],
        'city': [fake.city() for _ in range(num_customers)]
    })
    customers.to_csv('customers.csv', index=False)

    # Products
    products = pd.DataFrame({
        'product_id': range(1, num_products+1),
        'name': [
            fake.word().capitalize() + " " + choice(
                ['Phone','Laptop','Shirt','Shoes','Lamp','Book','Ball','Toy','Watch','Bag']
            ) for _ in range(num_products)
        ],
        'category': [choice(categories) for _ in range(num_products)],
        'cost_price': [randint(10, 500) for _ in range(num_products)],
        'selling_price': [randint(50, 1500) for _ in range(num_products)]
    })
    products.to_csv('products.csv', index=False)

    # Orders
    orders_list = []
    for i in range(1, num_orders+1):
        product_id = randint(1, num_products)
        selling_price = products.loc[products['product_id']==product_id, 'selling_price'].values[0]
        orders_list.append({
            'order_id': i,
            'customer_id': randint(1, num_customers),
            'product_id': product_id,
            'order_date': start_date + datetime.timedelta(days=randint(0,364)),
            'quantity': randint(1,10),
            'price': selling_price
        })
    orders = pd.DataFrame(orders_list)
    orders.to_csv('orders.csv', index=False)

    # ---------- EXTRACT ----------
    customers = pd.read_csv('customers.csv')
    products = pd.read_csv('products.csv')
    orders = pd.read_csv('orders.csv')

    # ---------- TRANSFORM ----------
    orders.dropna(subset=['order_id','customer_id','product_id','order_date','quantity','price'], inplace=True)
    customers['city'] = customers['city'].fillna('Unknown')
    products['category'] = products['category'].fillna('Unknown')
    orders['order_date'] = pd.to_datetime(orders['order_date'])
    orders['revenue'] = orders['quantity'] * orders['price']

    # DimDate
    dates = pd.DataFrame({'date': orders['order_date'].unique()})
    dates['year'] = dates['date'].dt.year
    dates['month'] = dates['date'].dt.month
    dates['day'] = dates['date'].dt.day
    dates['quarter'] = dates['date'].dt.quarter
    dates.reset_index(inplace=True)
    dates.rename(columns={'index':'date_id'}, inplace=True)
    dates['date_id'] += 1  # start from 1

    # FactSales
    orders = orders.merge(dates[['date_id','date']], left_on='order_date', right_on='date', how='left')
    fact_sales = orders[['order_id','customer_id','product_id','date_id','quantity','revenue']]

    # ---------- LOAD INTO MYSQL ----------
    engine = create_engine(db_config)
    with engine.connect() as conn:
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS dim_customer (
            customer_id INT PRIMARY KEY,
            name VARCHAR(100),
            email VARCHAR(100),
            city VARCHAR(50)
        );"""))
        
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS dim_product (
            product_id INT PRIMARY KEY,
            name VARCHAR(100),
            category VARCHAR(50),
            cost_price DECIMAL(10,2),
            selling_price DECIMAL(10,2)
        );"""))
        
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS dim_date (
            date_id INT PRIMARY KEY,
            date DATE UNIQUE,
            year INT,
            month INT,
            day INT,
            quarter INT
        );"""))
        
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS fact_sales (
            sale_id INT AUTO_INCREMENT PRIMARY KEY,
            order_id INT,
            customer_id INT,
            product_id INT,
            date_id INT,
            quantity INT,
            revenue DECIMAL(10,2),
            FOREIGN KEY (customer_id) REFERENCES dim_customer(customer_id),
            FOREIGN KEY (product_id) REFERENCES dim_product(product_id),
            FOREIGN KEY (date_id) REFERENCES dim_date(date_id)
        );"""))

        # Clean load
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))
        conn.execute(text("TRUNCATE TABLE fact_sales;"))
        conn.execute(text("TRUNCATE TABLE dim_date;"))
        conn.execute(text("TRUNCATE TABLE dim_product;"))
        conn.execute(text("TRUNCATE TABLE dim_customer;"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))
        conn.commit()

    # Insert data
    customers.to_sql('dim_customer', engine, if_exists='append', index=False)
    products.to_sql('dim_product', engine, if_exists='append', index=False)
    dates.to_sql('dim_date', engine, if_exists='append', index=False)
    fact_sales.to_sql('fact_sales', engine, if_exists='append', index=False)

    print("ETL complete and data loaded.")
    return engine

# ----------------- ANALYTICS QUERIES -----------------
def get_top_customers(engine):
    query = """
    SELECT c.name, SUM(f.revenue) AS total_spent
    FROM fact_sales f
    JOIN dim_customer c ON f.customer_id = c.customer_id
    GROUP BY c.name
    ORDER BY total_spent DESC
    LIMIT 5;
    """
    return pd.read_sql(text(query), engine)

def get_monthly_revenue(engine):
    query = """
    SELECT d.year, d.month, SUM(f.revenue) AS monthly_revenue
    FROM fact_sales f
    JOIN dim_date d ON f.date_id = d.date_id
    GROUP BY d.year, d.month
    ORDER BY d.year, d.month;
    """
    df = pd.read_sql(text(query), engine)
    df['month_label'] = df['year'].astype(str) + '-' + df['month'].astype(str).str.zfill(2)
    return df

def get_best_selling(engine):
    query = """
    SELECT p.name, SUM(f.quantity) AS total_sold
    FROM fact_sales f
    JOIN dim_product p ON f.product_id = p.product_id
    GROUP BY p.name
    ORDER BY total_sold DESC
    LIMIT 10;
    """
    return pd.read_sql(text(query), engine)

# ----------------- ADDITIONAL VISUALIZATIONS -----------------
def get_category_revenue(engine):
    query = """
    SELECT p.category, SUM(f.revenue) AS revenue
    FROM fact_sales f
    JOIN dim_product p ON f.product_id = p.product_id
    GROUP BY p.category
    ORDER BY revenue DESC;
    """
    return pd.read_sql(text(query), engine)

def get_avg_order_value(engine):
    query = """
    SELECT d.year, d.month, AVG(f.revenue) AS avg_order
    FROM fact_sales f
    JOIN dim_date d ON f.date_id = d.date_id
    GROUP BY d.year, d.month
    ORDER BY d.year, d.month;
    """
    df = pd.read_sql(text(query), engine)
    df['month_label'] = df['year'].astype(str) + '-' + df['month'].astype(str).str.zfill(2)
    return df

def get_orders_by_weekday(engine):
    query = """
    SELECT DAYNAME(d.date) AS weekday, COUNT(*) AS orders_count
    FROM fact_sales f
    JOIN dim_date d ON f.date_id = d.date_id
    GROUP BY weekday
    ORDER BY FIELD(weekday,'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday');
    """
    return pd.read_sql(text(query), engine)

def get_quantity_per_category(engine):
    query = """
    SELECT p.category, SUM(f.quantity) AS total_quantity
    FROM fact_sales f
    JOIN dim_product p ON f.product_id = p.product_id
    GROUP BY p.category
    ORDER BY total_quantity DESC;
    """
    return pd.read_sql(text(query), engine)

def get_top_cities(engine):
    query = """
    SELECT c.city, SUM(f.revenue) AS revenue
    FROM fact_sales f
    JOIN dim_customer c ON f.customer_id = c.customer_id
    GROUP BY c.city
    ORDER BY revenue DESC
    LIMIT 5;
    """
    return pd.read_sql(text(query), engine)

def get_customer_distribution(engine):
    query = """
    SELECT city, COUNT(*) AS customers_count
    FROM dim_customer
    GROUP BY city
    ORDER BY customers_count DESC;
    """
    return pd.read_sql(text(query), engine)

def get_price_quantity_scatter(engine):
    query = """
    SELECT p.selling_price, SUM(f.quantity) AS total_quantity
    FROM fact_sales f
    JOIN dim_product p ON f.product_id = p.product_id
    GROUP BY p.product_id;
    """
    return pd.read_sql(text(query), engine)

# ----------------- PLOT GENERATOR -----------------
def generate_plots(
    top_customers, monthly_revenue, best_selling,
    category_revenue, avg_order_value, orders_by_weekday,
    quantity_per_category, top_cities, customer_distribution,
    price_quantity_scatter
):
    sns.set(style="whitegrid")

    # Top Customers
    plt.figure(figsize=(8,5))
    sns.barplot(x='total_spent', y='name', data=top_customers, hue='name', dodge=False, palette='viridis')
    plt.title('Top 5 Customers by Total Spend')
    plt.legend([],[], frameon=False)
    plt.tight_layout()
    plt.savefig('static/plots/top_customers.png')
    plt.close()

    # Monthly Revenue
    plt.figure(figsize=(10,6))
    sns.lineplot(x='month_label', y='monthly_revenue', data=monthly_revenue, marker='o')
    plt.xticks(rotation=45)
    plt.title('Monthly Revenue Trend')
    plt.tight_layout()
    plt.savefig('static/plots/monthly_revenue.png')
    plt.close()

    # Best-Selling Products
    plt.figure(figsize=(10,6))
    sns.barplot(x='total_sold', y='name', data=best_selling, hue='name', dodge=False, palette='magma')
    plt.title('Top 10 Best-Selling Products')
    plt.legend([],[], frameon=False)
    plt.tight_layout()
    plt.savefig('static/plots/best_selling.png')
    plt.close()

    # Category Revenue
    plt.figure(figsize=(8,5))
    sns.barplot(x='revenue', y='category', data=category_revenue, palette='coolwarm', dodge=False)
    plt.title('Revenue by Product Category')
    plt.tight_layout()
    plt.savefig('static/plots/category_revenue.png')
    plt.close()

    # Avg Order Value Trend
    plt.figure(figsize=(10,6))
    sns.lineplot(x='month_label', y='avg_order', data=avg_order_value, marker='o')
    plt.xticks(rotation=45)
    plt.title('Average Order Value Trend')
    plt.tight_layout()
    plt.savefig('static/plots/avg_order_value.png')
    plt.close()

    # Orders per Weekday
    plt.figure(figsize=(8,5))
    sns.barplot(x='weekday', y='orders_count', data=orders_by_weekday, palette='Set2')
    plt.title('Orders per Day of Week')
    plt.tight_layout()
    plt.savefig('static/plots/orders_per_weekday.png')
    plt.close()

    # Quantity per Category
    plt.figure(figsize=(8,5))
    sns.barplot(x='total_quantity', y='category', data=quantity_per_category, palette='Set1', dodge=False)
    plt.title('Quantity Sold per Category')
    plt.tight_layout()
    plt.savefig('static/plots/quantity_per_category.png')
    plt.close()

    # Top Cities by Revenue
    plt.figure(figsize=(8,5))
    sns.barplot(x='revenue', y='city', data=top_cities, palette='Blues_d', dodge=False)
    plt.title('Top 5 Cities by Revenue')
    plt.tight_layout()
    plt.savefig('static/plots/top_cities.png')
    plt.close()

    # Customer Distribution (Updated)
    top_customers = customer_distribution.sort_values(by='customers_count', ascending=False).head(20)
    plt.figure(figsize=(10,6))
    sns.barplot(x='customers_count', y='city', data=top_customers, palette='Oranges_r', dodge=False)
    plt.title('Top 20 Cities by Customer Count')
    plt.xlabel('Number of Customers')
    plt.ylabel('City')
    plt.tight_layout()
    plt.savefig('static/plots/customer_distribution.png')
    plt.close()

    # Price vs Quantity Scatter
    plt.figure(figsize=(8,5))
    sns.scatterplot(x='selling_price', y='total_quantity', data=price_quantity_scatter, hue='total_quantity', palette='viridis', s=100)
    plt.title('Product Price vs Quantity Sold')
    plt.tight_layout()
    plt.savefig('static/plots/price_vs_quantity.png')
    plt.close()

    print("All plots generated in static/plots folder.")
