from app.ui.login_window import LoginWindow
from app.ui.main_window import MainWindow


def main() -> None:
    login = LoginWindow()
    login.mainloop()
    if not login.authenticated:
        return
    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
