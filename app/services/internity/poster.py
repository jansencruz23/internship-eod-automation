from datetime import date

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from app.schemas.report import InternityEOD


class InternityPoster:
    """Automates EOD form submission on aufccs.org using Playwright."""

    def __init__(self, username: str, password: str, form_url: str):
        self.username = username
        self.password = password
        self.form_url = form_url
        self.base_url = form_url.rsplit("/", 2)[0]  # https://aufccs.org

    def post(
        self, eod_data: InternityEOD, target_date: date, auto_submit: bool = False
    ) -> bool:
        """Automate the aufccs.org EOD form submission.

        Always opens a visible browser so the user can watch.
        After filling, shows a confirm dialog unless auto_submit is True.

        Args:
            eod_data: Structured EOD data from the LLM.
            target_date: The date to submit the report for.
            auto_submit: If True, submits immediately without asking.
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, slow_mo=300)
            page = browser.new_page()

            try:
                # Step 1: Login
                self._login(page)

                # Step 2: Navigate to EOD form
                print(f"[Internity] Navigating to {self.form_url}")
                page.goto(self.form_url, wait_until="domcontentloaded")
                # Wait for the form to actually render
                page.get_by_role("button", name="Submit Report").wait_for(
                    state="visible", timeout=10000
                )

                # Step 3: Fill tasks
                self._fill_tasks(page, eod_data.tasks)

                # Step 4: Fill text areas
                self._fill_field(page, "Key Successes", eod_data.key_successes)
                self._fill_field(page, "Main Challenges", eod_data.main_challenges)
                self._fill_field(
                    page, "Plans for Tomorrow", eod_data.plans_for_tomorrow
                )

                # Step 5: Submit or leave for user
                if auto_submit:
                    self._submit(page)
                    return True

                print(
                    "[Internity] Form filled! Review it in the browser.\n"
                    "  → Click 'Submit Report' yourself to submit, or close the browser to cancel."
                )
                # Wait for the user to either submit or close the browser
                page.wait_for_event("close", timeout=0)
                return True

            except PlaywrightTimeout as e:
                print(f"[Internity] Timeout during form submission: {e}")
                raise
            except Exception as e:
                print(f"[Internity] Error during form submission: {e}")
                raise
            finally:
                browser.close()

    def _login(self, page):
        """Navigate to login page and authenticate."""
        print("[Internity] Logging in...")
        page.goto(f"{self.base_url}/login", wait_until="domcontentloaded")

        page.locator("#email").fill(self.username)
        page.locator("#password").fill(self.password)
        page.get_by_role("button", name="Log in").click()

        # Verify login succeeded — should navigate away from /login
        page.wait_for_url(
            lambda url: "/login" not in url, timeout=10000
        )
        print("[Internity] Logged in successfully.")

    def _fill_tasks(self, page, tasks):
        """Fill repeatable task rows, clicking 'Add Another Task' as needed."""
        for i, task in enumerate(tasks):
            if i > 0:
                add_btn = page.get_by_role(
                    "button", name="Add Another Task"
                )
                add_btn.click()
                # Wait for the new task field to appear before filling
                page.get_by_placeholder("Task Description").nth(i).wait_for(
                    state="visible", timeout=5000
                )

            # --- CALIBRATE THESE SELECTORS ---
            # Based on the screenshot, fields use placeholder text.
            # Inspect the actual DOM and update if needed.
            desc_fields = page.get_by_placeholder("Task Description").all()
            if i < len(desc_fields):
                desc_fields[i].fill(task.description)

            hours_fields = page.get_by_placeholder("Hours").all()
            if i < len(hours_fields):
                hours_fields[i].fill(str(task.hours))

            minutes_fields = page.get_by_placeholder("Minutes").all()
            if i < len(minutes_fields):
                minutes_fields[i].fill(str(task.minutes))

            print(
                f"[Internity] Task {i + 1}: [{task.hours}h {task.minutes}m] "
                f"{task.description[:60]}..."
            )

    def _fill_field(self, page, label_text: str, value: str):
        """Fill a textarea by its placeholder or label text."""
        field = page.get_by_placeholder(label_text, exact=False)
        if field.count() > 0:
            field.first.fill(value)
            print(f"[Internity] Filled '{label_text}': {value[:60]}...")
            return

        field = page.get_by_label(label_text, exact=False)
        if field.count() > 0:
            field.first.fill(value)
            print(f"[Internity] Filled '{label_text}': {value[:60]}...")
            return

        print(f"[Internity] WARNING: Could not find field '{label_text}'")

    def _submit(self, page):
        """Click the submit button and verify submission succeeded."""
        submit_btn = page.get_by_role("button", name="Submit Report")
        submit_btn.click()

        # --- CALIBRATE THIS ASSERTION ---
        # Verify submission succeeded. Update to match the actual success
        # indicator on aufccs.org (success message, URL change, etc.)
        page.wait_for_url(
            lambda url: "end_of_day_reports/create" not in url, timeout=15000
        )
        print("[Internity] Form submitted successfully.")

    def test_connection(self, headed: bool = False) -> bool:
        """Test that login works without submitting anything.

        Args:
            headed: If True, launches visible browser with page.pause()
                    so you can inspect the DOM with Playwright Inspector.
        """
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=not headed)
                page = browser.new_page()

                if headed:
                    print("[Internity] Headed mode — navigating to login page...")
                    page.goto(f"{self.base_url}/login", wait_until="domcontentloaded")
                    print(
                        "[Internity] Pausing — use Playwright Inspector to inspect "
                        "the login form elements. Press Resume when done."
                    )
                    page.pause()
                    browser.close()
                    return True

                self._login(page)
                browser.close()
                return True
        except Exception as e:
            print(f"[Internity] Connection test failed: {e}")
            if not headed:
                try:
                    page.screenshot(path="debug_login.png")
                    print("[Internity] Screenshot saved to debug_login.png")
                except Exception:
                    pass
            return False
