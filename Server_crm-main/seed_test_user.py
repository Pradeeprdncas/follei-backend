import asyncio
import os
import sys
from datetime import datetime, timedelta

# Ensure correct import paths
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from database.connection import init_db, AsyncSessionLocal
from database.repository import CRMConnectionRepository
from oauth.crypto import CryptoUtil


async def seed():
    print("==================================================")
    print("   CRM GATEWAY - SEED TEST CUSTOMER CONNECTION    ")
    print("==================================================")
    
    # Initialize the database tables if they do not exist
    await init_db()
    
    user_id = "test_customer_1"
    provider = "hubspot"
    
    print(f"This script will configure a connection for User ID: '{user_id}' on Provider: '{provider}'.")
    print("You can pass real credentials (from your HubSpot sandbox/developer portal) or dummy values.")
    print("-" * 50)
    
    access_token = input("Enter Access Token [default: dummy-hubspot-token]: ").strip()
    if not access_token:
        access_token = "dummy-hubspot-token"
        
    refresh_token = input("Enter Refresh Token [default: dummy-refresh-token]: ").strip()
    if not refresh_token:
        refresh_token = "dummy-refresh-token"
        
    portal_id = input("Enter HubSpot Portal/Hub ID [default: 123456]: ").strip()
    if not portal_id:
        portal_id = "123456"
        
    portal_name = input("Enter Portal/Account Name [default: Test Sandbox Portal]: ").strip()
    if not portal_name:
        portal_name = "Test Sandbox Portal"
        
    # Encrypt the tokens using the CryptoUtil
    crypto = CryptoUtil()
    enc_access = crypto.encrypt(access_token)
    enc_refresh = crypto.encrypt(refresh_token)
    
    # Expiration set to 1 hour in the future
    expires_at = datetime.utcnow() + timedelta(hours=1)
    
    async with AsyncSessionLocal() as session:
        repo = CRMConnectionRepository(session)
        await repo.save_connection(
            user_id=user_id,
            provider=provider,
            access_token=enc_access,
            refresh_token=enc_refresh,
            expires_at=expires_at,
            scopes="crm.objects.contacts.read crm.objects.companies.read crm.objects.deals.read",
            account_id=portal_id,
            account_name=portal_name,
            metadata={"seeded": True}
        )
        await session.commit()
        
    print("-" * 50)
    print(f"[SUCCESS] Seeded connection for '{user_id}' successfully in SQLite database!")
    print(f"Stored encrypted tokens: {enc_access[:20]}... / {enc_refresh[:20]}...")
    print("\nTo retrieve CRM data for this customer, start your server and run:")
    print("curl -X GET \"http://127.0.0.1:8000/contacts\" \\")
    print(f"  -H \"X-CRM-Provider: {provider}\" \\")
    print(f"  -H \"X-User-ID: {user_id}\"")
    print("==================================================")


if __name__ == "__main__":
    asyncio.run(seed())
