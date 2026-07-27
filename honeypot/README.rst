.. _honeypot:
========
Honeypot
========

Guía del cog ``Honeypot``. Esta guía contiene la lista de comandos disponibles.
A lo largo de esta guía, ``[p]`` representa tu prefijo. Reemplaza ``[p]`` por tu propio prefijo al usar estos comandos en Discord.

.. note::

    Asegúrate de estar actualizado ejecutando ``[p]cog update honeypot``.
    Si algo falta o necesita mejoras en esta documentación, no dudes en crear un issue `aquí <https://github.com/killerbite95/killerbite-cogs/issues>`_.
    Esta documentación se genera cada vez que el cog recibe una actualización.

---------------
Sobre este cog:
---------------

Crea un canal en la parte superior del servidor para atraer selfbots/estafadores y notificar/mutear/expulsar/baneearlos inmediatamente.

---------
Comandos:
---------

Aquí están todos los comandos incluidos en este cog (11):

* ``[p]sethoneypot``
 Configura los ajustes del honeypot. Solo el dueño del servidor puede usar este comando por razones de seguridad.

* ``[p]sethoneypot action <acción>``
 La acción a tomar cuando se detecta un selfbot/estafador.

* ``[p]sethoneypot bandeletemessagedays <días>``
 El número de días de mensajes a baneear cuando se banea un selfbot/estafador.

* ``[p]sethoneypot createchannel``
 Crea el canal honeypot.

* ``[p]sethoneypot enabled <activar>``
 Activa o desactiva el cog.

* ``[p]sethoneypot logschannel <canal>``
 El canal donde enviar los logs.

* ``[p]sethoneypot modalconfig [confirmación=False]``
 Configura todos los ajustes del cog con un Modal de Discord.

* ``[p]sethoneypot muterole <role>``
 El rol de mute a asignar a los selfbots/estafadores, si la acción es `mute`.

* ``[p]sethoneypot pingrole <role>``
 El rol a mencionar cuando se detecta un selfbot/estafador.

* ``[p]sethoneypot resetsetting <ajuste>``
 Resetea un ajuste.

* ``[p]sethoneypot showsettings [con_desarrollador=False]``
 Muestra todos los ajustes del cog con valores por defecto y actuales.

------------
Instalación
------------

Si no has agregado mi repo antes, agrégalo primero. Lo llamaremos "killerbite-cogs".

.. code-block:: ini

    [p]repo add killerbite-cogs https://github.com/killerbite95/killerbite-cogs

Ahora, podemos instalar Honeypot.

.. code-block:: ini

    [p]cog install killerbite-cogs honeypot

Una vez instalado, no se carga por default. Cárgalo ejecutando el siguiente comando:

.. code-block:: ini

    [p]load honeypot

----------------
Soporte:
----------------

Revisa mis docs `aquí <https://killerbite-cogs.readthedocs.io/en/latest/>`_.
Mencioname en el canal de soporte de killers si necesitas ayuda.
Además, siéntete libre de abrir un issue o pull request en este repo.

--------
Créditos:
--------

By Killerbite95
