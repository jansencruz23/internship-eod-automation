import httpx

from app.models.report import EODReport


class TeamsPoster:
    def __init__(self, power_automate_url: str):
        self.power_automate_url = power_automate_url

    def post(self, report: EODReport) -> bool:
        """Post an EOD report to the Teams group chat via Power Automate."""
        payload = {
            "date": report.date.strftime("%B %#d, %Y"),
            "message": report.narrative,
        }

        print("[Teams] Posting to Power Automate...")
        print(f"[Teams] Payload: {payload}")

        response = httpx.post(
            self.power_automate_url,
            json=payload,
            timeout=30,
        )

        print(f"[Teams] Response status: {response.status_code}")
        print(f"[Teams] Response body: {response.text[:500]}")

        response.raise_for_status()
        return True

    def test_connection(self) -> bool:
        """Send a test message to verify the Power Automate flow works."""
        payload = {
            "date": "Connection Test",
            "message": "EOD Reporter is connected. If you see this in your group chat, it's working!",
        }
        try:
            response = httpx.post(
                self.power_automate_url,
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            return True
        except Exception:
            return False
