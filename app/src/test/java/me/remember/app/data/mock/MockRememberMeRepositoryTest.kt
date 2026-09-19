package me.remember.app.data.mock

import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import me.remember.app.model.Loadable
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class MockRememberMeRepositoryTest {
    @Test fun repositoryProvidesHumanMemories()=runBlocking{
        val state=MockRememberMeRepository().memories().first()
        assertTrue(state is Loadable.Content)
        assertEquals(3,(state as Loadable.Content).value.size)
    }
}
