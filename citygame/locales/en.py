# locales/en.py

translations = {
    "help_title": "Ciudad Virtual Commands",
    "help_text": (
        "`game choose_role <role>` - Choose your role in the game (mafia, civilian, police).\n"
        "`game action` - Perform an action based on your role.\n"
        "`game work` - Work in your profession and earn money.\n"
        "`game achievements` - Show your achievements.\n"
        "`game leaderboard` - Show the player leaderboard.\n"
        "`game challenge @user` - Challenge another player.\n"
        "`game daily_mission` - Complete a daily mission.\n"
        "`game buy <item>` - Buy properties or items.\n"
        "`game inventory` - Show your properties and items.\n"
        "`game set_language <es|en>` - Set your preferred language.\n"
        "`game help` - Show this help message.\n"
    ),
    "admin_help_title": "Administrative Commands",
    "admin_help_text": (
        "`game admin change_role @user <role>` - Change a user's role.\n"
        "`game admin add_achievement @user <achievement>` - Add an achievement to a user.\n"
        "`game admin remove_achievement @user <achievement>` - Remove an achievement from a user.\n"
        "`game admin reset_user @user` - Reset a user's progress.\n"
        "`game multiplier <value>` - Set the economic multiplier.\n"
    ),
    "role_invalid": "Invalid role. Please choose between mafia, civilian, or police.",
    "role_selected": "You have chosen the role of **{role}**. Enjoy the game!",
    "role_changed": "{user}'s role has been changed to **{role}**.",
    "no_role": "You must first choose a role using the `game choose_role` command.",
    "action_title": "Action Performed",
    "action_mafia": "You have conducted an operation and earned {earnings} coins and {xp_gain} XP.",
    "action_civilian": "You have worked and earned {earnings} coins and {xp_gain} XP.",
    "action_police": "You have caught a mafia member and earned {earnings} coins and {xp_gain} XP.",
    "level_up_title": "Level Up!",
    "level_up": "Congratulations, you have reached level {level}!",
    "achievement_unlocked_title": "Achievement Unlocked!",
    "achievement_unlocked": "You have unlocked the achievement: **{achievement}**!",
    "achievement_added": "Achievement **{achievement}** has been added to {user}.",
    "achievement_removed": "Achievement **{achievement}** has been removed from {user}.",
    "achievement_already_exists": "The user already has this achievement.",
    "achievement_not_found": "The user does not have this achievement.",
    "no_achievements": "You haven't obtained any achievements yet.",
    "your_achievements_title": "Your Achievements",
    "your_achievements": "**Your achievements:**\n{achievements_list}",
    "no_leaderboard_data": "There is no data in the leaderboard yet.",
    "leaderboard_title": "🏆 Leaderboard by Achievements",
    "leaderboard_entry": "{idx}. {user_display_name} - {achievements_count} achievements\n",
    "cannot_challenge_self": "You cannot challenge yourself.",
    "challenge_issued": "{challenger} has challenged {member}!",
    "challenge_winner": "The winner of the challenge is **{winner}**!",
    "challenge_reward": "{winner} has won {earnings} coins.",
    "mission_title": "Daily Mission",
    "mission_success_robo_banco": "You have successfully robbed a bank! You earned {earnings} coins and {xp_gain} XP.",
    "mission_success_contrabando": "Smuggling completed! You earned {earnings} coins and {xp_gain} XP.",
    "mission_success_extorsion": "Extortion successful! You earned {earnings} coins and {xp_gain} XP.",
    "mission_success_entrega_paquete": "You delivered the package on time! You earned {earnings} coins and {xp_gain} XP.",
    "mission_success_trabajo_voluntario": "Volunteer work completed! You earned {earnings} coins and {xp_gain} XP.",
    "mission_success_estudiar": "Study completed! You earned {earnings} coins and {xp_gain} XP.",
    "mission_success_patrulla": "Successful patrol! You earned {earnings} coins and {xp_gain} XP.",
    "mission_success_investigacion": "Investigation completed! You earned {earnings} coins and {xp_gain} XP.",
    "mission_success_operativo": "Operation successful! You earned {earnings} coins and {xp_gain} XP.",
    "mission_failure": "Mission failed. Try again tomorrow.",
    "language_set": "Your language has been set to **{language}**.",
    "available_languages": "Available languages: {languages}",
    "achievement_first_step": "First Step",
    # New achievements
    "achievement_robo_banco": "Master Thief",
    "achievement_contrabando": "Expert Smuggler",
    "achievement_extorsion": "Extortion King",
    "achievement_entrega_paquete": "Reliable Messenger",
    "achievement_trabajo_voluntario": "Model Citizen",
    "achievement_estudiar": "Dedicated Student",
    "achievement_patrulla": "Law Guardian",
    "achievement_investigacion": "Clever Detective",
    "achievement_operativo": "Operation Specialist",
    "work_title": "Work",
    "work_success": "You have worked and earned {earnings} coins and {xp_gain} XP.",
    "caught_title": "You've Been Caught!",
    "caught_by_police": "You have been caught by the police and are in jail for 3 turns!",
    "in_jail_title": "In Jail",
    "in_jail": "You are in jail for {time} more turns.",
    "released_title": "Release",
    "released_from_jail": "You have been released from jail!",
    "item_not_found": "The item '{item}' does not exist. Available items: {items}.",
    "not_enough_money": "You don't have enough money to buy this item.",
    "purchase_title": "Purchase Completed",
    "purchase_success": "You have bought **{item}** for {price} coins.",
    "no_properties": "You have no properties or items.",
    "inventory_title": "Your Inventory",
    "invalid_multiplier": "Invalid value. The multiplier must be between 0.00 and 2.00.",
    "multiplier_set": "The economic multiplier has been set to {valor}.",
    "user_reset": "{user}'s progress has been reset.",
    "daily_mission_cooldown": "You have already completed your daily mission. Come back tomorrow.",
    "mission_cooldown": "You must wait {time} hours before doing another mission.",
    "language_not_supported": "The language '{language}' is not supported.",
    "command_on_cooldown": "This command is on cooldown. Please wait {time} seconds.",
}
