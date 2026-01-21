import random

def play():
    choices = ["rock", "paper", "scissors"]
    user_choice = input("Choose rock, paper, or scissors: ").lower()
    if user_choice not in choices:
        print("Invalid choice!")
        return
    comp_choice = random.choice(choices)
    print(f"Computer chose: {comp_choice}")
    if user_choice == comp_choice:
        print("It's a tie!")
    elif (user_choice == "rock" and comp_choice == "scissors") or \
         (user_choice == "paper" and comp_choice == "rock") or \
         (user_choice == "scissors" and comp_choice == "paper"):
        print("You win!")
    else:
        print("You lose!")
