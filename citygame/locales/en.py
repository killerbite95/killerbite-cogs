# locales/en.py

translations = {
    # General
    "help_title": "City Virtual Help",
    "help_text": (
        "Welcome to **City Virtual**. Here you can choose to be mafia, "
        "civilian, or police and participate in various activities.\n\n"
        "**Available Commands:**\n"
        "!game set_language <es/en> - Set your preferred language.\n"
        "!game choose_role <role> - Choose your role in the game.\n"
        "!game action - Perform an action according to your role.\n"
        "!game work - Work to earn coins.\n"
        "!game daily_mission - Get your daily mission.\n"
        "!game achievements - Show your achievements.\n"
        "!game leaderboard - Show the player leaderboard.\n"
        "!game challenge @user - Challenge another player.\n"
        "!game buy <item> - Buy an item from the shop.\n"
        "!game inventory - Show your inventory.\n"
        "\n**Administrative Commands:**\n"
        "!game admin change_role @user <role> - Change a user's role.\n"
        "!game admin add_achievement @user <achievement> - Add an achievement to a user.\n"
        "!game admin remove_achievement @user <achievement> - Remove an achievement from a user.\n"
        "!game admin reset_user @user - Reset a user's progress.\n"
        "!game admin cooldown <command> <time> - Change a command's cooldown.\n"
        "!game admin multiplier <action/work> <value> - Set the economic multiplier.\n"
        "!game admin release @user - Release a user from jail."
    ),
    "language_set": "Your language has been set to '{language}'.",
    "no_role": (
        "You haven't chosen a role. Please choose a role using "
        "!game choose_role <role>."
    ),
    "role_invalid": (
        "The role entered is not valid. Available roles are mafia, civilian, and police."
    ),
    "role_selected": "You have chosen the role of **{role}**.",
    "no_achievements": "You haven't earned any achievements yet.",
    "achievements_title": "Your Achievements",
    "inventory_empty": "Your inventory is empty.",
    "inventory_title": "Your Inventory",
    "no_leaderboard_data": "There is not enough data to display the leaderboard.",
    "leaderboard_title": "Player Leaderboard",
    "item_not_found": "The specified item does not exist in the shop.",
    "not_enough_money": "You do not have enough coins to purchase this item.",
    "item_purchased": "You have successfully purchased **{item}**.",
    "daily_mission_completed": "You have already completed your daily mission.",
    "daily_mission_in_progress": (
        "You already have a daily mission in progress: **{mission}**."
    ),
    "daily_mission_assigned": (
        "A new daily mission has been assigned to you: **{mission}**."
    ),
    "level_up_title": "Level Up!",
    "level_up": "Congratulations! You have reached level {level}.",
    "released_title": "You Have Been Released",
    "released_from_jail": (
        "You have served your time in jail and are now free."
    ),
    "released_admin": (
        "You have been released from jail by an administrator."
    ),
    "in_jail_title": "You Are in Jail",
    "in_jail": (
        "You must wait {time} minutes before you can perform this action."
    ),
    "caught_title": "You've Been Caught!",
    "caught_by_police": (
        "The police have caught you during your illegal activities. "
        "You'll be in jail for 3 minutes."
    ),
    "action_title": "Action",
    "action_mafia": (
        "You have carried out a clandestine operation and earned {earnings} coins "
        "and {xp_gain} experience points."
    ),
    "action_civilian": (
        "You have worked honestly and earned {earnings} coins "
        "and {xp_gain} experience points."
    ),
    "action_police": (
        "You have patrolled the city and earned {earnings} coins "
        "and {xp_gain} experience points."
    ),
    "work_title": "Work",
    "work_success": (
        "You have completed your work and earned {earnings} coins "
        "and {xp_gain} experience points."
    ),
    "challenge_result": "{winner} has won the challenge!",
    "challenge_sent": "You have sent a challenge to {opponent}.",
    # Enhanced Daily Missions
    "daily_missions": [
        "Capture 5 mafia members.",
        "Complete 3 successful jobs.",
        "Earn a total of 1000 coins.",
        "Reach level 5.",
        "Perform 10 actions.",
        "Challenge and win against another player.",
        "Buy 2 items from the shop.",
        "Win 500 coins in a single challenge.",
        "Level up 2 times.",
        "Complete a mission without failing.",
    ],
    # Administrative Help
    "admin_help": (
        "**Administrative Commands:**\n"
        "!game admin change_role @user <role> - Change a user's role.\n"
        "!game admin add_achievement @user <achievement> - Add an achievement to a user.\n"
        "!game admin remove_achievement @user <achievement> - Remove an achievement from a user.\n"
        "!game admin reset_user @user - Reset a user's progress.\n"
        "!game admin cooldown <command> <time> - Change a command's cooldown.\n"
        "!game admin multiplier <action/work> <value> - Set the economic multiplier.\n"
        "!game admin release @user - Release a user from jail."
    ),
    # New Translation for Admin Release
    "released_admin": "You have been released from jail by an administrator."
}
