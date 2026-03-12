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
        self, eod_data: InternityEOD, target_date: date, dry_run: bool = False
    ) -> bool:
        """Automate the aufccs.org EOD form submission.

        Args:
            eod_data: Structured EOD data from the LLM.
            target_date: The date to submit the report for.
            dry_run: If True, opens a visible browser and pauses before submit.
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not dry_run)
            page = browser.new_page()

            try:
                # Step 1: Login
                self._login(page)

                # Step 2: Navigate to EOD form
                print(f"[Internity] Navigating to {self.form_url}")
                page.goto(self.form_url, wait_until="networkidle")
                page.wait_for_timeout(1000)

                # Step 3: Fill tasks
                self._fill_tasks(page, eod_data.tasks)

                # Step 4: Fill text areas
                self._fill_field(page, "Key Successes", eod_data.key_successes)
                self._fill_field(page, "Main Challenges", eod_data.main_challenges)
                self._fill_field(
                    page, "Plans for Tomorrow", eod_data.plans_for_tomorrow
                )

                if dry_run:
                    print(
                        "[Internity] Dry run — form filled but NOT submitted. "
                        "Browser will stay open for 60 seconds for inspection."
                    )
                    page.wait_for_timeout(60_000)
                    return True

                # Step 5: Submit
                self._submit(page)
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
        page.goto(f"{self.base_url}/login", wait_until="networkidle")

        # --- CALIBRATE THESE SELECTORS ---
        # Inspect the actual login page and update if needed.
        page.fill(
            'input[type="email"], input[name="email"], input[name="username"]',
            self.username,
        )
        page.fill('input[type="password"], input[name="password"]', self.password)
        page.click('button[type="submit"], input[type="submit"]')
        page.wait_for_load_state("networkidle")
        print("[Internity] Logged in successfully.")

    def _fill_tasks(self, page, tasks):
        """Fill repeatable task rows, clicking 'Add Another Task' as needed."""
        for i, task in enumerate(tasks):
            if i > 0:
                add_btn = page.get_by_text("Add Another Task", exact=False)
                add_btn.click()
                page.wait_for_timeout(500)

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
        """Click the submit button and wait for confirmation."""
        submit_btn = page.get_by_text("Submit Report", exact=False)
        submit_btn.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        print("[Internity] Form submitted successfully.")

    def test_connection(self) -> bool:
        """Test that login works without submitting anything."""
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                self._login(page)
                browser.close()
                return True
        except Exception as e:
            print(f"[Internity] Connection test failed: {e}")
            return False
