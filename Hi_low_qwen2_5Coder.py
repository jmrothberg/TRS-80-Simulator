import random

def main():
    print("Welcome to the High-Low Game!")
    print("Guess the number between 1 and 100.")
    
    # Generate a random number between 1 and 100
    target_number = random.randint(1, 100)
    
    # Initialize the user's guess
    user_guess = None
    
    while True:
        try:
            user_guess = int(input("Your guess: "))
            
            if user_guess == target_number:
                print(f"Congratulations! You guessed the correct number {target_number}.")
                break
            elif user_guess < target_number:
                print("Too low! Try again.")
            else:
                print("Too high! Try again.")
                
            # Ask for another guess
            continue
            
        except ValueError:
            print("Invalid input! Please enter a valid integer.")
            continue
        
        # Break out of the loop if the user guesses correctly
        if user_guess == target_number:
            break

if __name__ == "__main__":
    main()