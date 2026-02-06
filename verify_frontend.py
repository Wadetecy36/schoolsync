from playwright.sync_api import sync_playwright, expect
import time

def verify_frontend():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        try:
            # 1. Login
            print("Logging in...")
            page.goto("http://localhost:5000/login")
            page.fill('input[name="username"]', "admin")
            page.fill('input[name="password"]', "Admin@123")
            page.click('button[type="submit"]')

            # Wait for dashboard
            expect(page).to_have_url("http://localhost:5000/")
            print("Login successful.")

            # 2. Take screenshot of Dashboard
            page.wait_for_selector('#total-students')
            time.sleep(2) # Give some time for JS to load data
            page.screenshot(path="/home/jules/verification/dashboard.png")
            print("Dashboard screenshot saved.")

            # 3. Go to Students page
            page.goto("http://localhost:5000/students")
            page.wait_for_selector('#students-grid-view')
            time.sleep(2) # Give some time for JS to load data
            page.screenshot(path="/home/jules/verification/students.png")
            print("Students page screenshot saved.")

        except Exception as e:
            print(f"Error during verification: {e}")
            page.screenshot(path="/home/jules/verification/error.png")
        finally:
            browser.close()

if __name__ == "__main__":
    import os
    os.makedirs("/home/jules/verification", exist_ok=True)
    verify_frontend()
