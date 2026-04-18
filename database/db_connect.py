from db_utils import get_connection

def main():
    try:
        conn = get_connection()
        conn.close()
        print("DB connection successful.")
    except Exception as exc:
        print(f"DB connection failed: {exc}")


if __name__ == "__main__":
    main()
