import asyncio
import httpx
import config


async def main():
    if not config.PAYSTACK_SECRET_KEY:
        print("PAYSTACK_SECRET_KEY is not configured.")
        print("This is a manual Paystack smoke test and requires a Paystack API key.")
        return

    headers = {
        "Authorization": f"Bearer {config.PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "email": "test@example.com",
        "amount": 10000,
        "reference": "AIOS_TEST_002",
        "currency": "NGN",
        "callback_url": f"{config.PUBLIC_BASE_URL}/paystack/callback",
    }

    print("Testing Paystack...")
    print("API:", "https://api.paystack.co/transaction/initialize")
    print("Amount:", payload["amount"], "kobo")
    print("Currency:", payload["currency"])
    print("Callback:", payload["callback_url"])

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            "https://api.paystack.co/transaction/initialize",
            json=payload,
            headers=headers,
        )

    print("\nHTTP STATUS:", response.status_code)
    print("PAYSTACK RESPONSE:")
    print(response.text)


if __name__ == "__main__":
    asyncio.run(main())
