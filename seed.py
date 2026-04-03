import asyncio
from sqlalchemy import select
from app.core.db import AsyncSessionLocal
from app.core.security import hash_password
from app.core.permissions import ALL_PERMISSIONS, DEFAULT_ROLES
from app.models.auth import User, Role, Permission


async def seed_database():
    async with AsyncSessionLocal() as db:
        print("🌱 Starting database seed...")

        print("📝 Creating permissions...")
        permissions_map = {}
        for perm_data in ALL_PERMISSIONS:
            result = await db.execute(select(Permission).where(Permission.code == perm_data["code"]))
            existing_perm = result.scalar_one_or_none()

            if not existing_perm:
                perm = Permission(
                    code=perm_data["code"],
                    description=perm_data["description"],
                )
                db.add(perm)
                await db.flush()
                permissions_map[perm_data["code"]] = perm
                print(f"  ✅ Created permission: {perm_data['code']}")
            else:
                permissions_map[perm_data["code"]] = existing_perm
                print(f"  ⏭️  Permission exists: {perm_data['code']}")

        await db.commit()

        print("\n👥 Creating default roles...")
        for role_name, role_config in DEFAULT_ROLES.items():
            result = await db.execute(select(Role).where(Role.name == role_name))
            existing_role = result.scalar_one_or_none()

            if not existing_role:
                role = Role(
                    name=role_name,
                    description=role_config["description"],
                )

                if role_config["permissions"]:
                    role_permissions = [
                        permissions_map[perm_code]
                        for perm_code in role_config["permissions"]
                        if perm_code in permissions_map
                    ]
                    role.permissions = role_permissions

                db.add(role)
                await db.flush()
                # print(f"  ✅ Created role: {role_name} with {len(role_permissions)} permissions")

            else:
                print(f"  ⏭️  Role exists: {role_name}")

        await db.commit()

        print("\n🔐 Creating super admin user...")
        result = await db.execute(select(User).where(User.phone == "+998901234567"))
        existing_admin = result.scalar_one_or_none()

        if not existing_admin:
            super_admin = User(
                phone="+998901234567",
                email="string",
                full_name="Super Admin",
                hashed_password=hash_password("string"),
                is_super_admin=True,
            )
            db.add(super_admin)
            await db.commit()
            print("  ✅ Created super admin user")
            print("  📱 Phone: +998901234567")
            print("  🔑 Password: admin123")
            print("  ⚠️  PLEASE CHANGE THE PASSWORD IMMEDIATELY!")
        else:
            print("  ⏭️  Super admin already exists")

        print("\n✨ Database seeding completed!\n")


if __name__ == "__main__":
    asyncio.run(seed_database())
