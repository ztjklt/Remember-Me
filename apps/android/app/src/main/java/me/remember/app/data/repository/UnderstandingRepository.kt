package me.remember.app.data.repository

import kotlinx.coroutines.flow.Flow
import me.remember.app.model.Loadable
import me.remember.app.model.PersonModelView

/** The understanding shell consumes authorized Backend snapshots through this boundary. */
interface UnderstandingRepository {
    fun understanding(): Flow<Loadable<PersonModelView>>
}
