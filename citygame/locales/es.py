# locales/es.py

translations = {
    "help_title": "Comandos de Ciudad Virtual",
    "help_text": (
        "`juego elegir_rol <rol>` - Elige tu rol en el juego (mafia, civil, policía).\n"
        "`juego accion` - Realiza una acción según tu rol.\n"
        "`juego trabajar` - Trabaja en tu profesión y gana dinero.\n"
        "`juego logros` - Muestra tus logros.\n"
        "`juego clasificacion` - Muestra la clasificación de jugadores.\n"
        "`juego desafiar @usuario` - Desafía a otro jugador.\n"
        "`juego mision_diaria` - Completa una misión diaria.\n"
        "`juego comprar <item>` - Compra propiedades u objetos.\n"
        "`juego inventario` - Muestra tus propiedades y objetos.\n"
        "`juego establecer_idioma <es|en>` - Establece tu idioma preferido.\n"
        "`juego ayuda` - Muestra este mensaje de ayuda.\n"
    ),
    "admin_help_title": "Comandos Administrativos",
    "admin_help_text": (
        "`juego admin cambiar_rol @usuario <rol>` - Cambia el rol de un usuario.\n"
        "`juego admin añadir_logro @usuario <logro>` - Añade un logro a un usuario.\n"
        "`juego admin quitar_logro @usuario <logro>` - Quita un logro de un usuario.\n"
        "`juego admin restablecer_usuario @usuario` - Restablece el progreso de un usuario.\n"
        "`juego multiplicador <valor>` - Establece el multiplicador económico.\n"
    ),
    "role_invalid": "Rol inválido. Por favor, elige entre mafia, civil o policía.",
    "role_selected": "Has elegido el rol de **{role}**. ¡Diviértete en el juego!",
    "role_changed": "El rol de {user} ha sido cambiado a **{role}**.",
    "no_role": "Primero debes elegir un rol usando el comando `juego elegir_rol`.",
    "action_title": "Acción Realizada",
    "action_mafia": "Has realizado una operación y ganado {earnings} monedas y {xp_gain} XP.",
    "action_civilian": "Has trabajado y ganado {earnings} monedas y {xp_gain} XP.",
    "action_police": "Has atrapado a un miembro de la mafia y ganado {earnings} monedas y {xp_gain} XP.",
    "level_up_title": "¡Nivel Superior!",
    "level_up": "¡Felicidades, has subido al nivel {level}!",
    "achievement_unlocked_title": "¡Logro Desbloqueado!",
    "achievement_unlocked": "¡Has obtenido el logro: **{achievement}**!",
    "achievement_added": "El logro **{achievement}** ha sido añadido a {user}.",
    "achievement_removed": "El logro **{achievement}** ha sido removido de {user}.",
    "achievement_already_exists": "El usuario ya tiene este logro.",
    "achievement_not_found": "El usuario no tiene este logro.",
    "no_achievements": "Aún no has obtenido ningún logro.",
    "your_achievements_title": "Tus Logros",
    "your_achievements": "**Tus logros:**\n{achievements_list}",
    "no_leaderboard_data": "No hay datos en la clasificación aún.",
    "leaderboard_title": "🏆 Clasificación por Logros",
    "leaderboard_entry": "{idx}. {user_display_name} - {achievements_count} logros\n",
    "cannot_challenge_self": "No puedes desafiarte a ti mismo.",
    "challenge_issued": "¡{challenger} ha desafiado a {member}!",
    "challenge_winner": "El ganador del desafío es **{winner}**!",
    "challenge_reward": "{winner} ha ganado {earnings} monedas.",
    "mission_title": "Misión Diaria",
    "mission_success_robo_banco": "¡Has robado un banco exitosamente! Ganaste {earnings} monedas y {xp_gain} XP.",
    "mission_success_contrabando": "¡Contrabando completado! Ganaste {earnings} monedas y {xp_gain} XP.",
    "mission_success_extorsion": "¡Extorsión exitosa! Ganaste {earnings} monedas y {xp_gain} XP.",
    "mission_success_entrega_paquete": "¡Entregaste el paquete a tiempo! Ganaste {earnings} monedas y {xp_gain} XP.",
    "mission_success_trabajo_voluntario": "¡Trabajo voluntario completado! Ganaste {earnings} monedas y {xp_gain} XP.",
    "mission_success_estudiar": "¡Estudio completado! Ganaste {earnings} monedas y {xp_gain} XP.",
    "mission_success_patrulla": "¡Patrulla exitosa! Ganaste {earnings} monedas y {xp_gain} XP.",
    "mission_success_investigacion": "¡Investigación completada! Ganaste {earnings} monedas y {xp_gain} XP.",
    "mission_success_operativo": "¡Operativo exitoso! Ganaste {earnings} monedas y {xp_gain} XP.",
    "mission_failure": "Misión fallida. Intenta nuevamente mañana.",
    "language_set": "Tu idioma ha sido establecido a **{language}**.",
    "available_languages": "Idiomas disponibles: {languages}",
    "achievement_first_step": "Primer Paso",
    # Nuevos logros
    "achievement_robo_banco": "Maestro del Robo",
    "achievement_contrabando": "Contrabandista Experto",
    "achievement_extorsion": "Rey de la Extorsión",
    "achievement_entrega_paquete": "Mensajero Confiable",
    "achievement_trabajo_voluntario": "Ciudadano Ejemplar",
    "achievement_estudiar": "Estudiante Dedicado",
    "achievement_patrulla": "Guardían de la Ley",
    "achievement_investigacion": "Detective Astuto",
    "achievement_operativo": "Operativo Especialista",
    "work_title": "Trabajo",
    "work_success": "Has trabajado y ganado {earnings} monedas y {xp_gain} XP.",
    "caught_title": "¡Has sido Capturado!",
    "caught_by_police": "¡Has sido atrapado por la policía y estás en la cárcel por 3 turnos!",
    "in_jail_title": "En la Cárcel",
    "in_jail": "Estás en la cárcel por {time} turnos más.",
    "released_title": "Liberación",
    "released_from_jail": "¡Has sido liberado de la cárcel!",
    "item_not_found": "El objeto '{item}' no existe. Artículos disponibles: {items}.",
    "not_enough_money": "No tienes suficiente dinero para comprar este objeto.",
    "purchase_title": "Compra Realizada",
    "purchase_success": "Has comprado **{item}** por {price} monedas.",
    "no_properties": "No tienes propiedades u objetos.",
    "inventory_title": "Tu Inventario",
    "invalid_multiplier": "Valor inválido. El multiplicador debe estar entre 0.00 y 2.00.",
    "multiplier_set": "El multiplicador económico ha sido establecido a {valor}.",
    "user_reset": "El progreso de {user} ha sido restablecido.",
    "daily_mission_cooldown": "Ya has completado tu misión diaria. Vuelve mañana.",
    "mission_cooldown": "Debes esperar {time} horas antes de realizar otra misión.",
    "language_not_supported": "El idioma '{language}' no es compatible.",
    "command_on_cooldown": "Este comando está en cooldown. Por favor, espera {time} segundos.",
}
