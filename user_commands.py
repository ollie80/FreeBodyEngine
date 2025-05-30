
def example_command(args: list[str], command: str):
    print(f"This is an example command, you can run it using the command `freebody {command[0][0]}`.")

commands = [[["test", "hello"], example_command]]