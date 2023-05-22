from playwright.sync_api import Page, expect
import pytest

# TODO: Make this configurable
ROOT_URL = "http://localhost:5000"


@pytest.fixture()
def registered_user(page: Page, faker):
    email = faker.email()
    password = faker.password()
    page.goto(f"{ROOT_URL}/register")
    page.get_by_test_id("input_email").fill(email)
    page.get_by_test_id("input_password").fill(password)
    page.get_by_test_id("input_confirm_password").fill(password)
    page.get_by_test_id("button_register").click()
    return email, password


def test_register(page: Page, registered_user):
    locator = page.get_by_test_id("div_alert")
    expect(locator).to_have_text("User created. Please login.")


def test_register_mismatch_passwords(page: Page):
    page.goto(f"{ROOT_URL}/register")
    page.get_by_test_id("input_email").fill("user@domain.com")
    page.get_by_test_id("input_password").fill("password")
    page.get_by_test_id("input_confirm_password").fill("password2")
    page.get_by_test_id("button_register").click()
    locator = page.get_by_test_id("div_alert")
    expect(locator).to_have_text("Passwords must match.")


def test_login_required(page: Page):
    page.goto(f"{ROOT_URL}/logout")
    page.goto(f"{ROOT_URL}/")
    expect(page.get_by_test_id("div_alert")).to_have_text(
        "Please log in to access this page."
    )


def test_login(page: Page, registered_user):
    email = registered_user[0]
    password = registered_user[1]
    page.goto(f"{ROOT_URL}/login")
    page.get_by_test_id("input_email").fill(email)
    page.get_by_test_id("input_password").fill(password)
    page.get_by_test_id("button_login").click()
    expect(page.get_by_test_id("div_addclip")).to_be_visible()


def test_invalid_credentials(page: Page):
    page.goto(f"{ROOT_URL}/login")
    page.get_by_test_id("input_email").fill("invalid_email@domain.com")
    page.get_by_test_id("input_password").fill("invalid_password")
    page.get_by_test_id("button_login").click()
    expect(page.get_by_test_id("div_alert")).to_have_text("Invalid credentials.")
