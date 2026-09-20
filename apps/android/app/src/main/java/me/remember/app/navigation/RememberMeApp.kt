package me.remember.app.navigation

import androidx.compose.runtime.*
import androidx.navigation.compose.*
import me.remember.app.feature.*

@Composable fun RememberMeApp(){
    val nav=rememberNavController()
    NavHost(nav,Routes.Splash){
        composable(Routes.Splash){SplashScreen{nav.navigate(Routes.Welcome){popUpTo(Routes.Splash){inclusive=true}}}}
        composable(Routes.Welcome){WelcomeScreen{nav.navigate(Routes.Explain)}}
        composable(Routes.Explain){ExplanationScreen{nav.navigate(Routes.Consent)}}
        composable(Routes.Consent){ConsentScreen{nav.navigate(Routes.Introduce)}}
        composable(Routes.Introduce){IntroduceScreen{nav.navigate(Routes.Recording)}}
        composable(Routes.Recording){RecordingScreen{nav.navigate(Routes.Processing)}}
        composable(Routes.Processing){ProcessingScreen{nav.navigate(Routes.Birth)}}
        composable(Routes.Birth){TwinBirthScreen{nav.navigate(Routes.Voice)}}
        composable(Routes.Voice){VoiceSeedScreen{nav.navigate(Routes.Home){popUpTo(Routes.Welcome){inclusive=true}}}}
        composable(Routes.Home){CreatorHomeScreen(nav::navigate)}
        composable(Routes.Memories){MemoriesScreen{nav.popBackStack()}}
        composable(Routes.Twin){TwinScreen{nav.popBackStack()}}
        composable(Routes.Calibration){CalibrationScreen{nav.popBackStack()}}
        composable(Routes.Handover){HandoverScreen{nav.popBackStack()}}
        composable(Routes.Legacy){LegacyHomeScreen{nav.navigate(Routes.Twin)}}
        composable(Routes.Debug){DemoMenuScreen(nav::navigate){nav.popBackStack()}}
    }
}
