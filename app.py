# ----------------- app.py -----------------
from flask import Flask, render_template
from sqlalchemy import create_engine, text
import pandas as pd
from sales_etl_pipeline import (
    run_etl, get_top_customers, get_monthly_revenue, get_best_selling,
    generate_plots, get_category_revenue, get_avg_order_value,
    get_orders_by_weekday, get_quantity_per_category, get_top_cities,
    get_customer_distribution, get_price_quantity_scatter
)

app = Flask(__name__)

# ---------- DATABASE CONFIG ----------
DB_USER = 'root'
DB_PASSWORD = '123456'  # replace with your password
DB_HOST = 'localhost'
DB_PORT = '3306'
DB_NAME = 'salesdb'

db_config = f'mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'

# ---------- GLOBAL ENGINE ----------
engine = create_engine(db_config)

# ---------- ROUTES ----------
@app.route('/')
def home():
    return render_template('index.html')


@app.route('/etl')
def etl():
    """Run ETL pipeline and load database"""
    run_etl(db_config)  # ETL will populate DB
    return render_template("etl.html")


@app.route('/data/<table_name>')
def view_data(table_name):
    """View raw data from DB tables"""
    valid_tables = ['dim_customer', 'dim_product', 'dim_date', 'fact_sales']
    if table_name not in valid_tables:
        return f"<h3>Invalid table: {table_name}</h3>", 404

    engine = create_engine(db_config)
    with engine.connect() as conn:
        df = pd.read_sql(text(f"SELECT * FROM {table_name} LIMIT 500"), conn)

    # Convert to HTML with proper Bootstrap classes
    table_html = df.to_html(
        classes="table table-striped table-hover table-bordered table-sm text-center",
        index=False,
        justify="center",  # aligns headers and data properly
        border=0
    )

    return render_template('data_view.html', table_name=table_name, tables=table_html)


@app.route('/analytics')
def analytics():
    """Run analytics queries, generate plots, auto-run ETL if DB empty"""

    # Check if fact_sales table has data
    with engine.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) FROM fact_sales"))
        check = result.scalar()

    if check == 0:
        run_etl(db_config)

    # Original analytics
    top_customers = get_top_customers(engine)
    monthly_revenue = get_monthly_revenue(engine)
    best_selling = get_best_selling(engine)

    # Additional analytics / visualizations
    category_revenue = get_category_revenue(engine)
    avg_order_value = get_avg_order_value(engine)
    orders_by_weekday = get_orders_by_weekday(engine)
    quantity_per_category = get_quantity_per_category(engine)
    top_cities = get_top_cities(engine)
    customer_distribution = get_customer_distribution(engine)
    price_quantity_scatter = get_price_quantity_scatter(engine)

    # Generate all plots in static/plots
    generate_plots(
        top_customers, monthly_revenue, best_selling,
        category_revenue, avg_order_value, orders_by_weekday,
        quantity_per_category, top_cities, customer_distribution,
        price_quantity_scatter
    )

    return render_template('analytics.html')


# ---------- RUN APP ----------
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
